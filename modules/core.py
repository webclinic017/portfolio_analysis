# Author : Vikas Chouhan (presentisgood@gmail.com)

import json
import pprint
import sys
import re
import http
import urllib, json
from   urllib.request import urlopen, Request
from   urllib.error import URLError
import socket
import datetime
import pandas
import argparse
import copy
import time
import os
import math
import csv
import contextlib, warnings
import shutil
from   colorama import Fore, Back, Style
import datetime as datetime
import numpy as np
import logging
from   subprocess import call, check_call
import requests
from   bs4 import BeautifulSoup
import itertools

from   .utils import dropzero, cfloat, vprint, split_date_range_into_chunks
from   dateutil.relativedelta import relativedelta, TH

#################################################################
# GLOBALS
headers = {'User-agent' : 'Mozilla/5.0'}
sleep_time = 4

##################################################################
# MARKETSMOJO.COM functions
def pull_info_from_marketsmojo(scrip):
    url_search = 'https://www.marketsmojo.com/portfolio-plus/frontendsearch?SearchPhrase={}'
    url_front  = 'https://www.marketsmojo.com'
    company_l  = []

    req_this   = requests.get(url_search.format(scrip))
    if req_this.json() == []:
        print('Nothing found for {} !!'.format(scrip))
        return None
    # endif

    # Go over all of them
    for item_this in req_this.json():
        url_page = url_front + item_this[u'url']
        company  = item_this[u'Company'].replace('<b>', '').replace('</b>', '')
        bse_code = int(item_this[u'ScriptCode'])
        nse_code = item_this[u'Symbol']
        pg_this  = requests.get(url_page)

        # Parse using beautifulsoup
        html_page = BeautifulSoup(pg_this.text, 'html.parser')
        ##
        try:
            valuation = html_page.find('div', {'class' : 'valuation cf'}).text.replace('\n', ' ').rstrip(' ').strip(' ')
            quality   = html_page.find('div', {'class' : 'quality cf'}).text.replace('\n', ' ').rstrip(' ').strip(' ')
            fin_trend = html_page.find('div', {'class' : 'financials cf'}).text.replace('\n', ' ').rstrip(' ').strip(' ')
        except AttributeError:
            valuation = ''
            quality   = ''
            fin_trend = ''
        # endtry

        company_l.append({
                             "name"         : company,
                             "bsecode"      : bse_code,
                             "nse_code"     : nse_code,
                             "valuation"    : valuation,
                             "quality"      : quality,
                             "fintrend"     : fin_trend,
                        })
    # endfor

    return company_l
# enddef

##################################################################
# INVESTING.COM FUNCTIONS
#

sock = "bcbf3d08f70aaf07b860dc2f481beee5/1473605026"
res_tbl = {
              "1m"     : 1,
              "5m"     : 5,
              "15m"    : 15,
              "30m"    : 30,
              "1h"     : 60,
              "4h"     : 240,
              "5h"     : 300,
              "1D"     : "D",
              "1W"     : "W",
              "1M"     : "M",
          }

def g_sock():
    urlt = g_burlb()
    with contextlib.closing(urlopen(urlt)) as s:
        return '/'.join(re.search('carrier=(\w+)&time=(\d+)&', s.read().decode('utf-8')).groups())
    # endwith
    assert(False)
# enddef
def init_sock():
    global sock
    sock = g_sock()
# enddef

def g_burlb():
    return "http://tvc4.forexpros.com"
def g_burl(soc_idf):
    return g_burlb() + "/{}/1/1/8/history?".format(soc_idf)
def g_bsurl(soc_idf):
    return g_burlb() + "/{}/1/1/8/symbols?".format(soc_idf)
def g_surl(soc_idf):
    return g_burlb() + "/{}/1/1/8/search?".format(soc_idf)

def strdate_to_unixdate(str_date):
    return int(time.mktime(datetime.datetime.strptime(str_date, '%d/%m/%Y').timetuple()))
# enddef

def unixdate_now():
    return int(time.mktime(datetime.datetime.now().timetuple()))
# enddef
def strdate_now():
    return datetime.datetime.now().strftime("%a, %d %b %Y %H:%M:%S")
# enddef

# Fetch from investing.com
def fetch_data(ticker, resl, t_from=None, t_timeout=4):
    if t_from == None:
        t_from = strdate_to_unixdate("01/01/2000")
    else:
        t_from = strdate_to_unixdate(t_from)
    # endif
    ftch_tout = 5
    t_indx    = 0

    assert(resl in res_tbl.keys())

    while t_indx < ftch_tout:
        t_to     = unixdate_now()
        this_url = g_burl(sock) + "symbol={}&resolution={}&from={}&to={}".format(ticker, res_tbl[resl], t_from, t_to)

        logging.debug("{} : Fetching {}".format(strdate_now(), this_url))
        try:
            this_req = Request(this_url, None, headers)
            response = urlopen(this_req, timeout=t_timeout)
            j_data   = json.loads(response.read())
            if not bool(j_data):
                logging.debug("{} : Not able to fetch.".format(strdate_now()))
                logging.debug("{} : Returned {}".format(strdate_now(), j_data))
            else:
                break
            # endif
        except socket.error:
            # Just try again after a pause if encountered an 104 error
            logging.debug('Encountered socket error. Retrying after {} seconds..'.format(sleep_time))
            time.sleep(sleep_time)
        except URLError:
            logging.debug('Encountered timeout error. Retrying after {} seconds..'.format(sleep_time))
            time.sleep(sleep_time)
        # endtry
        t_indx   = t_indx + 1
    # endwhile

    if (t_indx >= ftch_tout):
        logging.debug("{} : Retries exceeded !!".format(strdate_now()))
        # Exit
        sys.exit(-1)
    # endif

    # Get basic pb_frame
    def g_pdbase(j_data):
        x_alt_a  = range(0, len(j_data['c']))
        t_data   = [ datetime.datetime.fromtimestamp(int(x)) for x in j_data['t'] ]
        d_frame  = pandas.DataFrame(index=x_alt_a)
    
        d_frame['c'] = j_data['c']
        d_frame['o'] = j_data['o']
        d_frame['h'] = j_data['h']
        d_frame['l'] = j_data['l']
        d_frame['t'] = t_data
        d_frame['T'] = j_data['t']

        if 'v' in j_data:
            d_frame['v']  = j_data['v']
        # endif
        if 'vo' in j_data:
            d_frame['vo'] = j_data['vo']
        # endif
    
        return d_frame
    # enddef

    #print "{} : Fetched data. done !!".format(strdate_now())
    # Enclosed within try except block to print the data incase some exception happens
    try:
        return dropzero(g_pdbase(j_data))
    except Exception as e:
        # Debug info
        print('** Exception encountered in fetch_data(). Returned j_data = {}'.format(j_data))
        return g_pdbase({'c' : [], 'o' : [], 'h' : [], 'l' : [], 'v' : [], 'vo' : [], 't' : [], 'T' : []})
    # endtry
# enddef

def scan_security_by_symbol(sym, exchg="NS"):
    this_url = g_surl(sock) + "query={}&exchange={}".format(sym, exchg)

    #print "{} : Fetching {}".format(strdate_now(), this_url)
    response = urlopen(this_url)
    j_data   = json.loads(response.read())
    if not bool(j_data):
        print("{} : Not able to fetch. Returned data = {}".format(strdate_now(), j_data))
        sys.exit(-1)
    else:
        for item in j_data:
            if item["symbol"] == sym:
                return item["description"], item["ticker"]
            # endif
        # endfor
        return None
    # endif
# enddef

def scan_security_by_name(name, exchg_list=['NS', 'BO', 'MCX', 'NCDEX']):
    this_url_fmt = g_surl(sock) + "query={}&exchange={}"
    j_data_f     = []

    # Iterate over all exchanges
    for exchg_this in exchg_list:
        this_url = this_url_fmt.format(name, exchg_this)
        #print "{} : Fetching {}".format(strdate_now(), this_url)
        response = urlopen(this_url)
        j_data   = json.loads(response.read())
        if not bool(j_data):
            continue
        else:
            j_data_f = j_data_f + j_data
        # endif
    # endfor
    return j_data_f
# enddef

##############################################################################################
# Option chain
# This is pretty hacked up code. Need to clean it up !!
def last_thu(month_incr=0):
    if month_incr > 2:
        print('month_incr should be between 0 & 2')
        sys.exit(-1)
    # endif
    todayte = datetime.datetime.today()
    if (todayte.month + month_incr) % 12 == 0:
        cmon = 12
        cyear = todayte.year
    else:
        cmon    = (todayte.month + month_incr) % 12
        if cmon < todayte.month:
            cyear = todayte.year + 1
        else:
            cyear = todayte.year
        # endif
    # endif
    #print 'cmon = {}'.format(cmon)
    t = None
    
    for i in range(1, 24):
        t = todayte + relativedelta(weekday=TH(i))
        #print 't = {}'.format(t)
        #print 't.mon = {}'.format(t.month)
        #print 'cmon = {}'.format(cmon)
        if datetime.datetime(t.year, t.month, 1) > datetime.datetime(cyear, cmon, 1):
            # since t is exceeded we need last one  which we can get by subtracting -2 since it is already a Thursday.
            t = t + relativedelta(weekday=TH(-2))
            break
        # endif
    # endfor
    return t
# enddef

# Miniaturized version of last_thu
def last_thu2(month_incr=0):
    return  datetime.date.today() + relativedelta(day=1, months=+1, days=-1) + relativedelta(months=month_incr) + relativedelta(weekday=TH(-1))
# enddef

def last_thu_opt_tbl(month_incr=0):
    if month_incr > 2 or month_incr < 0:
        print('month_incr should be between 0 to 2.')
        sys.exit(-1)
    # endif
    return last_thu2(month_incr)
# enddef

def last_thu_str(month_incr=0, historical=False):
    mon_l   = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    exp_day = last_thu2(month_incr) if historical else last_thu_opt_tbl(month_incr)
    return '{}{}{}'.format(exp_day.day, mon_l[exp_day.month-1], exp_day.year)
# enddef
    
def option_table(symbol='NIFTY', month=0, instrument=None, verbose=False):
    #url_this = 'https://www.nseindia.com/live_market/dynaContent/live_watch/option_chain/optionKeys.jsp?segmentLink=17&instrument=OPTIDX&symbol={}&date={}'
    url_this = 'https://www.nseindia.com/live_market/dynaContent/live_watch/option_chain/optionKeys.jsp?symbol={}&instrument={}&date={}&segmentLink=17&segmentLink=17'
    hdr_this = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
                'Accept-Encoding': 'none',
                'Accept-Language': 'en-US,en;q=0.8',
                'Connection': 'keep-alive'}
    header_l = [ 
                 'OI', 'Chng in OI', 'Volume', 'IV', 'LTP', 'Net Chng', 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty',
                 'Strike Price',
                 'Bid Qty', 'Bid Price', 'Ask Price', 'Ask Qty', 'Net Chg', 'LTP', 'IV', 'Volume', 'Chng in OI', 'OI'
               ]
    header_m = [
                 'Call_OI', 'Call_Chng_in_OI', 'Call_Volume', 'Call_IV', 'Call_LTP',
                 'Call_Net_Chng', 'Call_Bid_Qty', 'Call_Bid_Price', 'Call_AskPrice', 'Call_Ask_Qty',
                 'Strike_Price',
                 'Put_Bid_Qty', 'Put_Bid_Price', 'Put_Ask_Price', 'Put_Ask_Qty', 'Put_Net_Chg',
                 'Put_LTP', 'Put_IV', 'Put_Volume', 'Put_Chng_in_OI', 'Put_OI'
               ]

    # Decide upon instrument type
    if instrument == None:
        if symbol in ['NIFTY']:
            print('Using OPTIDX for {}.'.format(symbol))
            instrument = 'OPTIDX'
        else:
            print('Using OPTSTK for {}.'.format(symbol))
            instrument = 'OPTSTK'
        # endif
    else:
        if instrument not in ['OPTIDX', 'OPTSTK']:
            print('Invalid instrument type passed {}'.format(instrument))
            sys.exit(-1)
        # endif
    # endif

    act_url  = url_this.format(symbol, instrument, last_thu_str(month))
    vprint('Fetching from {}'.format(act_url), verbose)
    req_this = Request(act_url, headers=hdr_this)
    page     = urlopen(req_this)
    s_this   = page.read()
    soup     = BeautifulSoup(s_this, 'lxml')
    tbl_l    = soup.findAll('table')
    tr_l     = tbl_l[2].findAll('tr')

    new_tbl_l = []
    for i in range(0, len(tr_l)):
        if i == 0 or i == 1 or i == (len(tr_l) - 1):
            continue
        # endif
        d_l = [ cfloat(x.text.strip('\r\n\t ').replace(',', '')) for x in tr_l[i].findAll('td')]
        # First and last columns are junk
        d_l = d_l[1:-1]
        new_tbl_l.append(d_l)
    # endfor

    # Form pandas dataframe
    frame_t = pandas.DataFrame()
    for h_indx_t in range(len(header_m)):
        h_t = header_m[h_indx_t]
        c_t = [item[h_indx_t] for item in new_tbl_l]
        frame_t[h_t] = c_t
    # endfor
    # Replace all empty cells by nan
    frame_t.replace('-', np.nan, inplace=True)

    return frame_t
# enddef

# Get major support and resistance levels from option chain
def option_levels(option_table):
    new_table = option_table.set_index('Strike_Price')
    # Get strike prices for highest call OI and put OI
    resistance = cfloat(new_table.loc[new_table['Call_OI'] == new_table['Call_OI'].max()].index[0])
    support = cfloat(new_table.loc[new_table['Put_OI'] == new_table['Put_OI'].max()].index[0])

    return {'R1' : resistance, 'S1' : support}
# enddef

# Options historical data
def option_historical(symbol, option_type, month=0, instrument=None, verbose=False, date_range='24month'):
    url_this = 'https://nseindia.com/products/dynaContent/common/productsSymbolMapping.jsp?instrumentType={}&symbol={}&expiryDate={}&optionType={}&strikePrice=&dateRange={}&fromDate=&toDate=&segmentLink=9&symbolCount='
    if option_type not in ['PE', 'CE']:
        print('option_type can be either PE or CE')
        sys.exit(-1)
    # endif
    # Decide upon instrument type
    if instrument == None:
        if symbol in ['NIFTY']:
            print('Using OPTIDX for {}.'.format(symbol))
            instrument = 'OPTIDX'
        else:
            print('Using OPTSTK for {}.'.format(symbol))
            instrument = 'OPTSTK'
        # endif
    else:
        if instrument not in ['OPTIDX', 'OPTSTK']:
            print('Invalid instrument type passed {}'.format(instrument))
            sys.exit(-1)
        # endif
    # endif
    exp_date = last_thu2(month).strftime('%d-%m-%Y')
    url_act = url_this.format(instrument, symbol, exp_date, option_type, date_range)

    vprint('Fetching from {}'.format(url_act), verbose)
    session = requests.Session()
    headers = {'Referer' : 'https://nseindia.com/products/content/derivatives/equities/historical_fo.htm' ,
               'Accept-Encoding' : 'gzip, deflate, br',
               'User-Agent' : 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:64.0) Gecko/20100101 Firefox/64.0'}
    resp_t  = session.get(url_act, headers=headers)
    soup_t  = BeautifulSoup(resp_t.text, 'lxml')
    csv_ele = soup_t.find('div', {'id' : 'csvContentDiv'})
    csv_ele_t = csv_ele.text.replace('"', '')

    if csv_ele_t == '':
        return None
    # endif
    data_t = [x.split(',') for x in csv_ele_t.split(':')]
    # Check if last element is not the same size as first one. If not remove it
    data_t = data_t[:-2] if len(data_t[-1]) != len(data_t[0]) else data_t

    # Convert to dataframe
    dataframe_t = pandas.DataFrame()
    for i in range(len(data_t[0])):
        dataframe_t[data_t[0][i]] = [x[i] for x in data_t[1:]]
    # endfor

    return dataframe_t
# enddef


########################################################################################
# Zerodha Kite functions
res_tbl_zk = {
              "1m"     : 'minute',
              "5m"     : '5minute',
              "15m"    : '15minute',
              "30m"    : '30minute',
              "1h"     : '60minute',
              "2h"     : '2hour',
              "4h"     : '4hour',
              "5h"     : '5hour',
              "1D"     : 'day',
              "1W"     : 'week',
          }

def g_burlb_kite():
    return "https://kitecharts-aws.zerodha.com/api/chart"

# Fetch from Zerodha Kite
def fetch_data_kite(ticker, resl, public_token, t_from=None, range_days=400, t_timeout=25, sleep_time=14, verbose=False):
    if t_from == None:
        t_from = "2000-01-01"
    # endif
    ftch_tout = 15
    t_indx    = 0

    t_to      = datetime.datetime.now().strftime('%Y-%m-%d')
    dt_range  = split_date_range_into_chunks((t_from, t_to), date_fmt="%Y-%m-%d", range_days=range_days, order='dec')

    assert(resl in res_tbl_zk.keys())

    data_list = []
    finish    = False
    for drange_t in dt_range:
        while t_indx < ftch_tout:
            try:
                this_url = g_burlb_kite() + "/{}/{}?from={}&to={}&oi=1&public_token={}&access_token=".format(ticker,
                        res_tbl_zk[resl], drange_t[0], drange_t[1], public_token)

                logging.debug("{} : Fetching {}".format(strdate_now(), this_url))
                if verbose:
                    print('Fetching {}'.format(this_url))
                # endif
                response = requests.get(this_url, timeout=t_timeout, headers=headers)
                j_data   = json.loads(response.text)
                if not bool(j_data):
                    logging.debug("{} : Not able to fetch.".format(strdate_now()))
                    logging.debug("{} : Returned {}".format(strdate_now(), j_data))
                else:
                    # If we are returned empty data, flag finish
                    if len(j_data['data']['candles']) == 0:
                        finish = True
                        break
                    # endif

                    # Fetch data in list
                    data_list.append(j_data['data']['candles'])
                    break
                # endif
            except socket.error:
                # Just try again after a pause if encountered an 104 error
                logging.debug('Encountered socket error. Retrying after {} seconds..'.format(sleep_time))
                time.sleep(sleep_time)
            except URLError:
                logging.debug('Encountered timeout error. Retrying after {} seconds..'.format(sleep_time))
                time.sleep(sleep_time)
            except ValueError:
                logging.debug('Encountered value error. Retrying after {} seconds..'.format(sleep_time))
                time.sleep(sleep_time)
            except http.client.IncompleteRead:
                #print('ERROR:: Incomplete Read Error.', flush=True)
                logging.debug('Encountered IncompleteRead error. Retrying after {} seconds..'.format(sleep_time))
                time.sleep(sleep_time)
            # endtry
            t_indx   = t_indx + 1
        # endwhile

        if (t_indx >= ftch_tout):
            logging.debug("{} : Retries exceeded !!".format(strdate_now()))
            # Exit
            sys.exit(-1)
        # endif

        # Check finish flag
        if finish:
            break
        # endif
    # endfor

    # Populate full data
    data_list = list(reversed(data_list))
    # Flatten full list
    data_list = list(itertools.chain(*data_list))
    j_data['data']['candles'] = data_list

    # Get basic pb_frame
    def g_pdbase(j_data):
        data_list = j_data['data']['candles']
        # Data format = [timestamp, open, high, low, close, volume]

        date_l   = [x[0] for x in data_list]
        open_l   = [x[1] for x in data_list]
        high_l   = [x[2] for x in data_list]
        low_l    = [x[3] for x in data_list]
        close_l  = [x[4] for x in data_list]
        vol_l    = [x[5] for x in data_list]

        # Remove timezone information
        t_date   = [ datetime.datetime.strptime(x, "%Y-%m-%dT%H:%M:%S%z").strftime("%Y-%m-%d %H:%M:%S") for x in date_l ]
        d_frame  = pandas.DataFrame(index=t_date)
    
        d_frame['c'] = close_l
        d_frame['o'] = open_l
        d_frame['h'] = high_l
        d_frame['l'] = low_l
        d_frame['v'] = vol_l

        return d_frame
    # enddef

    #print "{} : Fetched data. done !!".format(strdate_now())
    # Enclosed within try except block to print the data incase some exception happens
    try:
        return dropzero(g_pdbase(j_data))
    except Exception as e:
        # Debug info
        print('** Exception encountered in fetch_data(). Returned j_data = {}'.format(j_data))
        return g_pdbase({'c' : [], 'o' : [], 'h' : [], 'l' : [], 'v' : []})
    # endtry
# enddef