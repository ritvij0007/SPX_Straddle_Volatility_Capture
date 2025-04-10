# -*- coding: utf-8 -*-
"""
Created on Thu Jan  9 22:58:30 2025

@author: ritvi
"""

import math
from scipy.stats import norm
import pandas as pd
from pandas.tseries.offsets import CustomBusinessDay
import json
import os
from pathlib import Path

script_directory = Path(__file__).parent.absolute()


class LoadData:
    def __init__(self, base_path=os.path.realpath(os.getcwd())):
        self.base_path = base_path
        self.static_data = None
        # Build the full path to the static data JSON file within the constructor
        self.json_file_path = os.path.join(self.base_path, 'Static_files', 'static_SPX_Straddle_Volatility_Capture.json')

    def load_static(self):
        """
        Load static configuration data from the JSON file located in the Static_files directory.
        """
        with open(self.json_file_path, 'r') as file:
            self.static_data = json.load(file)
        # print("Static data loaded:")
        return self.static_data

    def load_daily_state(self, date):
        """
        Load daily state data based on the date provided.
        The file is expected to be named in the format {date}_spx_strategy_daily_data.json
        """
        # Format the filename based on the date provided
        filename = f"{date.strftime('%Y-%m-%d')}_SPX_Straddle_Volatility_Capture_daily_data.json"
        daily_file_path = os.path.join(self.base_path, 'Daily_files', filename)
        
        try:
            with open(daily_file_path, 'r') as file:
                daily_data = json.load(file)
            # print(f"Daily data loaded from {daily_file_path}")
            # Assuming the structure contains a top-level key corresponding to 'spx_strategy' or similar
            index_data = daily_data['SPX_Straddle_Volatility_Capture']  # Adjust the key based on your actual structure
            return index_data['index_levels'], index_data['result']
        except FileNotFoundError:
            print(f"No file found for the specified date: {daily_file_path}")
            return None, None
        except json.JSONDecodeError:
            print(f"Error decoding JSON from the file: {daily_file_path}")
            return None, None
        except KeyError:
            print(f"Missing expected keys in the JSON data.")
            return None, None



class BlackScholes:
    def __init__(self, S, K, T, sigma, r=0.0):
        self.S = S        # Stock price
        self.K = K        # Strike price
        self.T = T        # Time to maturity in years
        self.sigma = sigma  # Volatility
        self.r = r      # Risk-free rate, default is 0.0

    def d1(self):
        """
        Calculate d1 used in the Black-Scholes formulas.
        """
        return (math.log(self.S / self.K) + (self.r + 0.5 * self.sigma ** 2) * self.T) / (self.sigma * math.sqrt(self.T))
    
    def d2(self):
        """
        Calculate d2 used in the Black-Scholes formulas.
        """
        return self.d1() - self.sigma * math.sqrt(self.T)

    def delta(self, option_type='call'):
        """
        Calculate the delta of the option.
        option_type: 'call' or 'put'
        """
        if option_type.lower() == 'call':
            return norm.cdf(self.d1())
        else:  # Assumes 'put'
            return norm.cdf(self.d1()) - 1

    def vega(self):
        """
        Calculate the vega of the option, which is the derivative of the option price with respect to volatility.
        """
        return self.S * norm.pdf(self.d1()) * math.sqrt(self.T)

    def theta(self, call=True):
        """
        Calculate the theta of the option, showing the sensitivity of the option price to time decay.
        call: Boolean indicating whether the option is a call or put.
        """
        if call:
            return (-self.S * norm.pdf(self.d1()) * self.sigma / (2 * math.sqrt(self.T))) - (self.r * self.K * math.exp(-self.r * self.T) * norm.cdf(self.d1()))
        else:
            return (-self.S * norm.pdf(self.d1()) * self.sigma / (2 * math.sqrt(self.T))) + (self.r * self.K * math.exp(-self.r * self.T) * norm.cdf(-self.d2()))

    def gamma(self):
        """
        Calculate the gamma of the option, indicating the rate of change of delta in response to price movements of the underlying asset.
        """
        return norm.pdf(self.d1()) / (self.S * self.sigma * math.sqrt(self.T))



def get_expiry(date, df):
    # Convert strings to datetime if they aren't already
    if isinstance(df['ExpiryDate'].iloc[0], str):
        df['ExpiryDate'] = pd.to_datetime(df['ExpiryDate'])
    if isinstance(date, str):
        date = pd.to_datetime(date)
    
    # Filter to get unique expiry dates greater than or equal to the given date
    future_expiries = df[df['AsOfDate'] >= date]['ExpiryDate'].unique()
    future_expiries = sorted(future_expiries)
    
    # Return the third expiry date if possible
    if len(future_expiries) >= 3:
        return future_expiries[2]
    else:
        return None
    
    
    
def select_strike(date, S, expiry, df):
    # Convert strings to datetime if they aren't already
    if isinstance(df['ExpiryDate'].iloc[0], str):
        df['ExpiryDate'] = pd.to_datetime(df['ExpiryDate'])
    if isinstance(date, str):
        date = pd.to_datetime(date)
    if isinstance(expiry, str):
        expiry = pd.to_datetime(expiry)
    
    # Filter the dataframe for the given AsOfDate and ExpiryDate
    filtered_df = df[(df['AsOfDate'] == date) & (df['ExpiryDate'] == expiry)]
    
    # Find the closest strike
    filtered_df['Dist'] = (filtered_df['Strike'] - S).abs()
    min_dist = filtered_df['Dist'].min()  # Find the minimum distance
    
    # Get the rows that have the minimum distance
    closest_strikes = filtered_df[filtered_df['Dist'] == min_dist]
    
    # If more than one strike is equally close, select the lowest one
    closest_strike = closest_strikes['Strike'].min()
    
    return closest_strike
    

def calc_date(start_date, end_date):
    # Load holiday data from Excel
    data_loader = LoadData()
    
    holiday_df = pd.read_excel(data_loader.load_static()['SPX_Straddle_Volatility_Capture']['holiday_file'])
    holidays = pd.to_datetime(holiday_df['Date'])

    # Define a custom business day using the loaded holidays
    custom_bday = CustomBusinessDay(holidays=holidays)

    # Calculate the range of business dates excluding weekends and holidays
    business_dates = pd.date_range(start=start_date, end=end_date, freq=custom_bday)

    return business_dates



def previous_business_date(current_date, business_dates):
    # Convert current_date to pandas datetime if it isn't already
    current_date = pd.to_datetime(current_date)
    
    # Check if current date is the start date (inception date)
    if current_date == business_dates[0]:
        return current_date
    
    # Find the index of the current date in the business_dates list
    # and return the previous date in the list
    try:
        current_index = business_dates.get_loc(current_date) 
        return business_dates[current_index - 1]
    except ValueError:
        # In case the current date is not a business day, find the last business day before the current date
        previous_date = business_dates[business_dates < current_date][-1]
        return previous_date
    
    
def save_daily_files(date, index, result, index_levels):
    try:
        # Directory where the files will be saved
        
        directory_path = LoadData().base_path + '\\Daily_files'

        # Ensure the directory exists
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)

        # Format the filename to include the date and index name
        filename = f"{date.strftime('%Y-%m-%d')}_SPX_Straddle_Volatility_Capture_daily_data.json"
        file_path = os.path.join(directory_path, filename)

        # Prepare the data to be saved
        data_to_save = {
            index: {
                'date':date.strftime('%Y-%m-%d'),
                'index_levels': index_levels,
                'result': result
            }
        }

        # Save the data to a JSON file
        with open(file_path, 'w') as file:
            json.dump(data_to_save, file, indent=4)

        # print(f"Data saved to {file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")




def convert_json_to_csv(folder_path, output_csv_name='combined_data.csv'):
    """
    Convert all JSON files in the specified folder to a single CSV file.

    Parameters:
    - folder_path: str, path to the folder containing JSON files.
    - output_csv_name: str, name of the output CSV file (default is 'combined_data.csv').
    """
    # Initialize a list to hold all rows for the final DataFrame
    all_rows = []
    index=[]
    input_path=folder_path+'\\Daily_files'
    # Loop through all files in the folder
    for filename in os.listdir(input_path):
        if filename.endswith('.json'):
            # Construct the full file path
            json_file_path = os.path.join(input_path, filename)
            
            # Read the JSON file
            with open(json_file_path, 'r') as file:
                data = json.load(file)
            
            # Extract the relevant information
            strategy_data = data['SPX_Straddle_Volatility_Capture']
            date = strategy_data['date']
            index_levels = strategy_data['index_levels']
            results = strategy_data['result']
            
            # Loop through the results dictionary
            for key, value in results.items():
                # Extract call and put data
                call_data = value.get('call', {})
                put_data = value.get('put', {})
                
                # Create a row for call options
                call_row = {
                    'date': date,
                    'result': key,
                    'Option': 'call',
                    **call_data,  # Unpack call data into the row
                }
                all_rows.append(call_row)
                index.append(index_levels)
                
                # Create a row for put options
                put_row = {
                    'date': date,
                    'result': key,
                    'Option': 'put',
                    **put_data,  # Unpack put data into the row
                }
                all_rows.append(put_row)
                index.append(index_levels)


    # Create a DataFrame from all rows
    final_df = pd.DataFrame(all_rows)

    # Add the index_levels column as the last column
    final_df['index_levels'] = index

    # Define the output CSV file path
    output_csv_path = os.path.join(folder_path, output_csv_name)

    # Save the DataFrame to a single CSV file
    final_df.to_csv(output_csv_path, index=False)

    print(f"All JSON files have been converted to a single CSV file: {output_csv_path}")
    return final_df







