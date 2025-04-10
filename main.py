# -*- coding: utf-8 -*-
"""
Created on Thu Jan  9 23:27:04 2025

@author: ritvi
"""
import sys
import pandas as pd
import warnings
warnings.filterwarnings('ignore')
from datetime import datetime
import time 
start_time = time.time()
# from pathlib import Path
import os
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor

# path = Path(__file__).parent.absolute()
sys.path.append(os.getcwd())
from helper import BlackScholes, get_expiry, select_strike, calc_date,LoadData,previous_business_date,save_daily_files,convert_json_to_csv


# function for just adding a conditional breakpoint
bp = lambda condition: breakpoint() if condition else None

loader = LoadData()

static_data=loader.load_static()
index_name='SPX_Straddle_Volatility_Capture'
inception_date=pd.to_datetime(static_data[index_name]['inception_date'])
end_date=pd.to_datetime(static_data[index_name]['end_date'])
start_date=inception_date




#can be changed
start_date=pd.to_datetime('2023-01-03')
end_date=pd.to_datetime('2023-01-03')
end_date=pd.to_datetime('2024-09-20')




business_date=calc_date(start_date,end_date)
business_dates=calc_date(inception_date,end_date)



class Portfolio:
    def __init__(self, date, df, vega_weight, business_dates, index_prev_close):
        self.date = pd.to_datetime(date)
        self.df = df
        self.vega_weight = vega_weight
        self.business_dates = business_dates
        self.index_prev_close = index_prev_close  # Directly passed to the constructor

        # Calculate the strategy's previous close using the previous business day's underlying price
        prev_business_day = previous_business_date(self.date, self.business_dates)
        self.strategy_previous_close = self.df[self.df['AsOfDate'] == prev_business_day]['UnderlyingPrice'].iloc[0]

    def calc_mtm(self,date,strip):
        if pd.to_datetime(strip['maturity'])==pd.to_datetime(date):
            if strip['delta_t'] >0:
                strip['Option_PnL'] = (strip['underlying_price_t']-strip['strike'] )*strip['units']   
            else:
                strip['Option_PnL'] = (strip['strike']-strip['underlying_price_t'] )*strip['units']                   
        else: 
            strip['Option_PnL'] = (strip['option_price_t']-strip['option_price_t_1'] )*strip['units']
            
        # strip['Option_PnL'] = (strip['option_price_t']-strip['option_price_t_1'] )*strip['units']            
        strip['Delta_PnL'] = (strip['underlying_price_t']-strip['underlying_t_1'] )*strip['units']*strip['delta_t_1']
        strip['Total_PnL']=strip['Option_PnL']-strip['Delta_PnL']
        return strip

    def compute_new_straddle(self):
        # Load data for the given date
        df_today = self.df[self.df['AsOfDate'] == self.date]
    
        # Calculate the third nearest maturity
        selected_maturity = get_expiry(self.date, df_today)
    
        # Find the closest strike based on the strategy's previous close
        closest_strike = select_strike(self.date, self.strategy_previous_close, selected_maturity, df_today)
    
        # Filter options for selected strike and maturity
        options_call = df_today[(df_today['Strike'] == closest_strike) & (df_today['OptionType'] == 'Call') & (df_today['ExpiryDate'] == selected_maturity)]
        options_put = df_today[(df_today['Strike'] == closest_strike) & (df_today['OptionType'] == 'Put') & (df_today['ExpiryDate'] == selected_maturity)]
    
        # Calculate Greeks and units for both call and put
        bs_call = BlackScholes(S=options_call['UnderlyingPrice'].iloc[0], K=closest_strike, T=(selected_maturity - self.date).days / 365, sigma=options_call['ImpliedVol'].iloc[0])
        bs_put = BlackScholes(S=options_put['UnderlyingPrice'].iloc[0], K=closest_strike, T=(selected_maturity - self.date).days / 365, sigma=options_put['ImpliedVol'].iloc[0])
    
        # Calculating deltas, gammas, and vegas
        delta_t_call = bs_call.delta('call')
        delta_t_put = bs_call.delta('put')
        gamma_call = bs_call.gamma()
        gamma_put = bs_put.gamma()
    
        vega_call = bs_call.vega()
        vega_put = bs_put.vega()
    
        units_call = -100 * (self.vega_weight * self.index_prev_close) / ((vega_call + vega_put)) ###* options_call['Price'].iloc[0])
        units_put = -100 * (self.vega_weight * self.index_prev_close) / ((vega_call + vega_put)) #### * options_put['Price'].iloc[0])
    
        # Time to expiry in years
        tau = (selected_maturity - self.date).days / 365
    
        # Creating dictionary structured as requested
        date_expiry_key = f"sv_{self.date.strftime('%Y-%m-%d')}_{selected_maturity.strftime('%Y-%m-%d')}"
        result = {
            date_expiry_key: {
                'call': {
                    'start_date':self.date.strftime('%Y-%m-%d'),
                    'strike': closest_strike,
                    'maturity': selected_maturity.strftime('%Y-%m-%d'),
                    'units': units_call,
                    'delta_t': delta_t_call,
                    'gamma': gamma_call,
                    'vega': vega_call,
                    'tau': tau,
                    'option_price_t': options_call['Price'].iloc[0],
                    'underlying_price_t': self.strategy_previous_close
                    
                },
                'put': {
                    'start_date':self.date.strftime('%Y-%m-%d'),
                    'strike': closest_strike,
                    'maturity': selected_maturity.strftime('%Y-%m-%d'),
                    'units': units_put,
                    'delta_t': delta_t_put,
                    'gamma': gamma_put,
                    'vega': vega_put,
                    'tau': tau,
                    'option_price_t': options_put['Price'].iloc[0],
                    'underlying_price_t': self.strategy_previous_close
                }
            }
        }
    
        return result


underlying_data=pd.read_excel(static_data[index_name]['underlying_file'],engine='openpyxl')
vega_weight=static_data[index_name]['vega_weight']


# Prev_Index_Levels, result = loader.load_daily_state(date)


Index_df=pd.DataFrame(index=business_date,columns=['Index Levels'])
for i in tqdm(business_date):
    # bp(i==pd.to_datetime("2023-01-13"))
    if i == inception_date:
        inception_level=static_data[index_name]['inception_level']
        portfolio = Portfolio(date=i, df=underlying_data,vega_weight=vega_weight,business_dates=business_dates,index_prev_close=inception_level)
        straddle_info = portfolio.compute_new_straddle()
        Index_levels=inception_level
        save_daily_files(i,index_name,straddle_info,index_levels=Index_levels)
        Index_df.loc[i]=Index_levels

    else:

        prev_bus_date=previous_business_date(i,business_dates)

        Prev_Index_Levels, result = loader.load_daily_state(prev_bus_date)
        portfolio = Portfolio(date=i, df=underlying_data,vega_weight=vega_weight,business_dates=business_dates,index_prev_close=Prev_Index_Levels)

        keys_to_remove = [key for key in result.keys() if datetime.strptime(key.split('_')[-1], '%Y-%m-%d') < i]
        for key in keys_to_remove:
            del result[key]
        all_total_PnL=0
        for key, option_types in result.items():
            Total_PnL=0
            for option_type, details in option_types.items():
                # Update the old key names to new ones
                details['delta_t_1'] = details.pop('delta_t')
                details['option_price_t_1'] = details.pop('option_price_t')
                details['underlying_t_1'] = details.pop('underlying_price_t')
                
                
                df_today = underlying_data[underlying_data['AsOfDate'] == i]
                new_data = df_today[(df_today['OptionType'] == option_type.capitalize()) & (df_today['Strike'] == details['strike']) & (df_today['ExpiryDate'] == details['maturity'])]
                sigma=new_data["ImpliedVol"].values[0]
                if not new_data.empty:
                    new_option_price = new_data['Price'].iloc[0]
                    new_underlying_price = new_data['UnderlyingPrice'].iloc[0]
                    
                    # Recalculate delta using a simplified approach or a full revaluation (simplified here)
                    bs = BlackScholes(S=new_underlying_price, K=details['strike'], T=details['tau'], sigma=sigma)  # Assuming a static sigma for illustration
                    details['delta_t'] = bs.delta(option_type)
                    details['option_price_t'] = new_option_price
                    details['underlying_price_t'] = new_underlying_price
                    details=portfolio.calc_mtm(i,details)
                    
                    # Pnl=+details['Total_PnL']
                Total_PnL=Total_PnL+details['Total_PnL']
                # print(Total_PnL,i,key)
            all_total_PnL=all_total_PnL+Total_PnL
        Index_levels=Prev_Index_Levels+all_total_PnL
        # print(Index_levels)
        Index_df.loc[i]=Index_levels
        portfolio = Portfolio(date=i, df=underlying_data,vega_weight=vega_weight,business_dates=business_dates,index_prev_close=Index_levels)
        straddle_info = portfolio.compute_new_straddle()
        result.update(straddle_info)
        save_daily_files(i,index_name,result,index_levels=Index_levels)



underlyings=convert_json_to_csv(os.getcwd())            
Index_df.to_csv(f"{os.getcwd()}\\Index_levels\\spx_strategy_{start_date.strftime('%Y-%m-%d')}_{end_date.strftime('%Y-%m-%d')}_run_time_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}.csv")

end_time = time.time() 
print(f'time taken to run this code is {end_time-start_time} seconds')

