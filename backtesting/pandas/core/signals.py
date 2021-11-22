import pandas as pd
import numpy as np
import re
import matplotlib.pyplot as plt
from   collections import OrderedDict
from   typing import AnyStr, Callable
import copy
from   modules.utils import *

# Disable chain assignment
pd.options.mode.chained_assignment = None

############################################################
# Constants
class SIGNAL:
    BUY    = 'Buy'
    SELL   = 'Sell'
    SHORT  = 'Short'
    COVER  = 'Cover'
# endclass

# Various kinds of Masks, depending on the naming convention used to define
# Signals
SIGNAL_MASK        = (SIGNAL.BUY, SIGNAL.SELL, SIGNAL.SHORT, SIGNAL.COVER)
SIGNAL_MASK2       = (SIGNAL.BUY, SIGNAL.SELL, SIGNAL.SELL, SIGNAL.BUY)
SIGNAL_MASK_LONG   = (SIGNAL.BUY, SIGNAL.SELL)
SIGNAL_MASK_SHORT  = (SIGNAL.SHORT, SIGNAL.COVER)
SIGNAL_MASK_SHORT2 = (SIGNAL.SELL, SIGNAL.BUY)

# Some keys
KEY_SIGNALS     = 'signals'
KEY_RPOSITIONS  = 'raw_positions'
KEY_POSITIONS   = 'positions'
KEY_SLIPPAGE    = 'slippage'
KEY_RUNMODE     = 'run_mode'
KEY_PRICES      = 'prices'
KEY_RETURNS     = 'returns'
KEY_STRATEGY    = 'strategy'
KEY_STRATPARAMS = 'strategy_params'
KEY_NPOINTS     = 'points'
KEY_PAVG_PRICE  = 'position_avg_price'

# shift parameter takes into account that we always buy or sell
# (i.e. take positions) on next bar
def set_buy(s, shift=True):
    s = s.shift().fillna(0) if shift else s.fillna(0)
    s.name = SIGNAL.BUY
    return s
# enddef
def set_sell(s, shift=True):
    s = s.shift().fillna(0) if shift else s.fillna(0)
    s.name = SIGNAL.SELL
    return s
# enddef
def set_short(s, shift=True):
    s = s.shift().fillna(0) if shift else s.fillna(0)
    s.name = SIGNAL.SHORT
    return s
# enddef
def set_cover(s, shift=True):
    s = s.shift().fillna(0) if shift else s.fillna(0)
    s.name = SIGNAL.COVER
    return s
# enddef

############################################################
# Signals to Position Generators using For loops
############################################################
# For loop based position generator for "any" mode
def _take_position_any(sig, pos, long_en, long_ex, short_en, short_ex):
    # check exit signals
    if pos != 0:  # if in position
        if pos > 0 and sig[long_ex]:  # if exit long signal
            pos -= sig[long_ex]
        elif pos < 0 and sig[short_ex]:  # if exit short signal
            pos += sig[short_ex]
        # endif
    # endif
    # check entry (possibly right after exit)
    if pos == 0:
        if sig[long_en]:
            pos += sig[long_en]
        elif sig[short_en]:
            pos -= sig[short_en]
        # endif
    # endif

    return pos
# enddef

# For loop based position generator for "long" mode
def _take_position_long(sig, pos, long_en, long_ex):
    # check exit signals
    if pos != 0:  # if in position
        if pos > 0 and sig[long_ex]:  # if exit long signal
            pos -= sig[long_ex]
        # endif
    # endif
    # check entry (possibly right after exit)
    if pos == 0:
        if sig[long_en]:
            pos += sig[long_en]
        # endif
    # endif

    return pos
# enddef

# For loop based position ggenerator for "short" mode
def _take_position_short(sig, pos, short_en, short_ex):
    # check exit signals
    if pos != 0:  # if in position
        if pos < 0 and sig[short_ex]:  # if exit short signal
            pos += sig[short_ex]
        # endif
    # endif
    # check entry (possibly right after exit)
    if pos == 0:
        if sig[short_en]:
            pos -= sig[short_en]
        # endif
    # endif

    return pos
# enddef

############################################################
# Signals to Position Generators using Vectorization
############################################################
# Vectorized positions generator
def _take_position_any_vec(sig, long_en, long_ex, short_en, short_ex):
    # Duplicate signals according to mask
    bs_sc_sigs = copy.copy(sig)[[long_en, long_ex, short_en, short_ex]].astype('int')
    bs_sc_sigs.columns = ['Buy', 'Sell', 'Short', 'Cover']
    bs_sigs   = bs_sc_sigs[['Buy', 'Sell']]
    sc_sigs   = bs_sc_sigs[['Short', 'Cover']]

    # Only start from the row where either we can take a long entry or a short entry.
    # Set all before rows to 0
    bs_sigs.loc[bs_sigs.index[0:bs_sigs.index.get_loc(bs_sigs[bs_sigs['Buy'] > 0].index[0])]] = 0
    sc_sigs.loc[sc_sigs.index[0:sc_sigs.index.get_loc(sc_sigs[sc_sigs['Short'] > 0].index[0])]] = 0

    # Generate positions
    long_pos_t  = (bs_sigs['Buy'] - bs_sigs['Sell']).cumsum()
    short_pos_t = (sc_sigs['Cover'] - sc_sigs['Short']).cumsum()
    return long_pos_t + short_pos_t
# enddef

# Vectorized positions generator
def _take_position_long_vec(sig, long_en, long_ex):
    # Duplicate signals according to mask
    bs_sc_sigs = copy.copy(sig)[[long_en, long_ex]].astype('int')
    bs_sc_sigs.columns = ['Buy', 'Sell']
    bs_sigs   = bs_sc_sigs

    # Only start from the row where either we can take a long entry or a short entry.
    # Set all before rows to 0
    bs_sigs.loc[bs_sigs.index[0:bs_sigs.index.get_loc(bs_sigs[bs_sigs['Buy'] > 0].index[0])]] = 0

    # Generate positions
    long_pos_t  = (bs_sigs['Buy'] - bs_sigs['Sell']).cumsum()
    return long_pos_t
# enddef

# Vectorized positions generator
def _take_position_short_vec(sig, short_en, short_ex):
    # Duplicate signals according to mask
    bs_sc_sigs = copy.copy(sig)[[short_en, short_ex]].astype('int')
    bs_sc_sigs.columns = ['Short', 'Cover']
    sc_sigs   = bs_sc_sigs

    # Only start from the row where either we can take a long entry or a short entry.
    # Set all before rows to 0
    sc_sigs.loc[sc_sigs.index[0:sc_sigs.index.get_loc(sc_sigs[sc_sigs['Short'] > 0].index[0])]] = 0

    # Generate positions
    short_pos_t  = (sc_sigs['Cover'] - sc_sigs['Short']).cumsum()
    return short_pos_t
# enddef

######################################
# Just arguments checking
def _check_signals_to_positions_args(mode, mask):
    mode_list = ['long', 'short', 'any']

    assert mode in mode_list, 'ERROR:: mode should be one of {}'.format(mode_list)
    if mode == 'any':
        assert len(mask) == 4 , 'ERROR:: in "any" mode, mask should be of 4 keys.'
    # endif
    assert len(mask) == 2 or len(mask) == 4, 'ERROR:: mask should be of 2 or 4 keys.'
# enddef

####################################################
# Signals to position generator
def signals_to_positions(signals, init_pos=0, mode='any', mask=SIGNAL_MASK, use_vec=True, shift=False):
    # Checks
    _check_signals_to_positions_args(mode, mask)

    pos = init_pos
    ps  = pd.Series(0., index=signals.index)
    tdi = {k:i for i,k in enumerate(signals.columns)}
    
    # Change string based mask to index mask for itertuples() when use_vec=True
    mask = [tdi[x] for x in mask] if not use_vec else mask

    if mode == 'any':
        long_en, long_ex, short_en, short_ex = mask
        if use_vec:
            ps = _take_position_any_vec(signals, long_en, long_ex, short_en, short_ex)
        else:
            for tup_t in signals.itertuples():
                pos   = _take_position_any(tup_t[1:], pos, long_en, long_ex, short_en, short_ex)
                ps[tup_t[0]] = pos
            # endfor
        # endif
    elif mode == 'long':
        long_en, long_ex = mask
        if use_vec:
            ps = _take_position_long_vec(signals, long_en, long_ex)
        else:
            for tup_t in signals.itertuples():
                pos   = _take_position_long(tup_t[1:], pos, long_en, long_ex)
                ps[tup_t[0]] = pos
            # endfor
        # endif
    elif mode == 'short':
        short_en, short_ex = mask
        if use_vec:
            ps = _take_position_short_vec(signals, short_en, short_ex)
        else:
            for tup_t in signals.itertuples():
                pos   = _take_position_short(tup_t[1:], pos, short_en, short_ex)
                ps[tup_t[0]] = pos
            # endfor
        # endif
    # endif

    # shift positions by 1, since the current position can only be liquidated on
    # next bar and vice-versa
    return ps.shift() if shift else ps
# enddef

########################################################
# Signals visualization
# check if all keys in plot_map are present in signals
def _check_plot_map_signals(signals, plot_map):
    not_present_keys = set(plot_map.keys()) - set(signals.columns)
    assert len(not_present_keys) == 0, '>> ERROR:: keys "{}" from plot_map not found in signals.'.format(not_present_keys)
# enddef

def _split_signals(signals, plot_map):
    # Check plot signals
    _check_plot_map_signals(signals, plot_map)

    sig_cols   = plot_map.keys()
    sig_cdata  = {}
    for sig_t in sig_cols:
        prow, ptype  = int(plot_map[sig_t][:-1]), plot_map[sig_t][-1]
        assert ptype in ['S', 'L'], '>> ERROR:: ptype should be one of "S, L"'
        if (prow, ptype) not in sig_cdata:
            sig_cdata[(prow, ptype)] = {}
        # endif
        # Take out the signal and add to it's appropriate category
        sig_cdata[(prow, ptype)][sig_t] = signals[sig_t]
    # endfor

    # Combine all series to dataframes
    for k,v in sig_cdata.items():
        sig_cdata[k] = pd.DataFrame(v)
    # endfor

    return OrderedDict(sig_cdata)
# enddef

# Plot Signals
# signals -> dataframe of signals with datetime as index
# sig_attr_map -> signal attributes map
#                 in form of {signal_name: 'xy'}
#                 where signal_name is the name of the signal (should match in signals dataframe)
#                 to be plotted. 'x' is the subplot number (as in 0,1,2 etc) and 'y' is either 'S' or 'L'
#                 'S' means that the plot is small in size, whereas 'L' means plot is large in size
def plot_signals(signals, sig_attr_map, sharex='all', dec_sig_ratio=0.2, remove_dates=False, date_name='Date'):
    # Change index name
    signals.index.name = date_name

    # Drop index if required
    signals     = signals.reset_index().drop(columns=[date_name]) if remove_dates else signals
    sigs_map    = _split_signals(signals, sig_attr_map)

    plots_len   = len(sigs_map.keys())
    ratios      = [dec_sig_ratio if x[1] == 'S' else (1-dec_sig_ratio) for x in sigs_map.keys()]
    fig, axes   = plt.subplots(plots_len, sharex=sharex, gridspec_kw={'height_ratios' : ratios})
    axes        = axes if isinstance(axes, np.ndarray) else np.array([axes])
    ax_ctr      = 0

    for sig_t in sigs_map:
        sigs_map[sig_t].plot(ax=axes[ax_ctr])
        ax_ctr += 1
    # endfor

    return fig
# enddef

# A wrapper for plot_signals which simplifies the api. In this plot,
# only two panes are plottted, Top one is larger one and plots price type signals
# Bottom one is smaller and plots oscillator type signals
def plot_signals_easy(psignals, osignals, remove_dates=False, rng=None):
    signals = pd.concat(psignals + osignals, axis=1)
    signals = signals.iloc[rng[0]:rng[1]] if rng else signals
    sig_attr_map = {**{k.name: '0L' for k in psignals}, **{k.name: '1S' for k in osignals}}
    plot_signals(signals, sig_attr_map, remove_dates=remove_dates)
# enddef

########################################################
# Calculate returns for a portfolio of assets given their
# individual returns
def calculate_portfolio_returns(returns, weights_list, log_returns=True):
    assert isinstance(returns, pd.DataFrame), 'ERROR::: returns should be a pandas dataframe of individual asset returns'
    assert len(returns.columns) == len(weights_list), 'ERROR:: Dimensions of weights_list should match that of number of columns in returns.'

    crets = np.log(np.dot(np.exp(returns), weights_list)) if log_returns else np.dot(returns, weights_list)
    return pd.Series(crets, index=returns.index)
# enddef

########################################################
# Slippage calculator
# NOTES:
# If nrets is of type log then :-
#     r = ln(y/x), without any slippage
# For slippage s, we have
#     r = ln(y/x(1+s)) for long and
#     r = ln(y/x(1-s)) for short, thus
#     r = ln(y/x) - ln(1+s) for long
#     r = ln(y/x) - ln(1-s) for short
# @args :-
#     pos        -> array of positions, 1 for long, -1 for short, 0 for out of market
#     rets       -> per bar returns of closing prices (daily returns if timeframe is daily)
#     slip       -> Slippage value (in %cenatge of closing prices if slip_perc=True)
#     ret_type   -> specify whether rets is normal returns or log returns
#     slip_perc  -> if True, slip is assumed as a %, else a fixed value in points
#     price      -> closig prices (only used when slippage is fixed.)
def apply_slippage(pos, rets, slip, ret_type='log', slip_perc=True, price=None):
    # Some checks
    if slip_perc == False:
        assert price is not None, 'ERROR:: price should not be None when slippage type is fixed.'
    # endif

    # Print information about how slippage is being calculated
    print('>> Using slippage {}{}'.format(slip, '%' if slip_perc else 'pts'))

    # Create new pandas df of rets and pos
    _df = pd.DataFrame(index=pos.index)
    _df['pos']   = pos
    _df['rets']  = rets
    _df['pos_d'] = pos.diff()
    pos_d        = _df['pos_d']
    if not price.empty:
        _df['price'] = price
    # endif

    # Get col maps. We moved from df.apply() to df.itertuples() due to speed issues.
    colm  = {k:i+1 for i,k in enumerate(_df.columns)}
    retss = []

    # Apply slippage
    if ret_type == 'log':
        if slip_perc:
            pos_slip = -np.log(1 + slip*0.01)
            neg_slip = -np.log(1 - slip*0.01)
            #retss    = pos * _df.apply(lambda x: x.rets + pos_slip if x.pos_d > 0 else \
            #               x.rets + neg_slip if x.pos_d < 0 else x.rets, axis=1)
            #####
            # Update : 22nd May 2020.
            # Fixed it second time. Switched the logic from apply() to itertuples()
            # since apparently itertuples() is so much faster than apply() for this
            # sort of logic
            #
            #for indx_t, tup_t in enumerate(_df.itertuples()):
            #    if tup_t[colm['pos_d']] > 0:
            #        retss.append(pos[indx_t] * (tup_t[colm['rets']] + pos_slip))
            #    elif tup_t[colm['pos_d']] < 0:
            #        retss.append(pos[indx_t] * (tup_t[colm['rets']] + neg_slip))
            #    else:
            #        retss.append(pos[indx_t] * tup_t[colm['rets']])
            #    # endif
            # endfor
            ##########
            # Update : 22nd May 2020.
            # Fixed it the 3rd time
            # Converted the above logic to full vectorized calculation.
            retss = pos * ((rets + pos_slip) * (pos_d > 0).astype('int') +  \
                           (rets + neg_slip) * (pos_d < 0).astype('int') +  \
                           rets * (pos_d == 0).astype('int'))
        else:
            #retss    = pos * _df.apply(lambda x: x.rets - np.log(1 + slip/x.price) if x.pos_d > 0 else \
            #               x.rets - np.log(1 - slip/x.price) if x.pos_d < 0 else x.rets, axis=1)
            ######
            # Update 22nd May 2020. Same as above reason
            #for indx_t, tup_t in enumerate(_df.itertuples()):
            #    if tup_t[colm['pos_d']] > 0:
            #        retss.append(pos[indx_t] * (tup_t[colm['rets']] - np.log(1 + slip/tup_t[colm['price']])))
            #    elif tup_t[colm['pos_d']] < 0:
            #        retss.append(pos[indx_t] * (tup_t[colm['rets']] - np.log(1 - slip/tup_t[colm['price']])))
            #    else:
            #        retss.append(pos[indx_t] * tup_t[colm['rets']])
            #    # endif
            ## endfor
            # Update 22nd May 2020. Same as above reason
            # FIXME: FIXME
            # TODO: This implementation is not tested yet !!!
            retss = ((rets - np.log(1 + slip/_df['price'])) * (pos_d > 0).astype('int') + \
                     (rets - np.log(1 - slip/_df['price'])) * (pos_d < 0).astype('int') + \
                     rets * (pos_d == 0).astype('int'))
        # endif
    else:
        raise ValueError('ERROR:: Only ret_type="log" is supported !!')
        #slip_u   = 0.01 * slip
        #retss    = pos * _df.apply(lambda x: (x.rets - slip_u)/(1 + slip_u) if x.pos_d > 0 else (x.rets + slip_u)/(1 - slip_u) if x.pos_d < 0 else x.rets, axis=1)
    # endif
    retss = pd.Series(retss, index=_df.index)
    return retss
# enddef


# Wrapper over apply_slippage. It accepts slippage in compact string form.
# Either in 'X', 'X%' or 'Xpts'
def apply_slippage_v2(pos, rets, slip, ret_type='log', price=None):
    slippage, slip_perc = extract_slippage(slip)
    return apply_slippage(pos, rets, slippage, ret_type, slip_perc, price)
# enddef

# Some utils
def extract_slippage(slip):
    assert isstring(slip), 'slippage={} should be of type string in form of X, X% or Xpts, where x is a float.'.format(slip)
    slip = slip.replace(' ', '')
    
    if slip[-1] == '%':
        return (float(slip[:-1]), True)
    elif slip[-3:].lower() == 'pts':
        return (float(slip[:-3]), False)
    else:
        try:
            return (float(slip), False)
        except:
            raise ValueError('slippage={} not in desired format X, X% or Xpts where X is a float'.format(slip))
        # endtry
    # endif
# enddef

###################################################################################
# Signals to position average price
###################################################################################
def __calc_avg_position_size_vec(pos, price, pos_type):
    assert pos_type in ['long', 'short'], 'pos_type can be one of [long, short].'

    pos_this = copy.copy(pos).fillna(0)
    if pos_type == 'long':
        pos_this[pos_this <= 0] = 0.0
    else:
        pos_this[pos_this >= 0] = 0.0
        pos_this[pos_this < 0]  *= -1.0
    # endif

    # Take negative of either long only or short only positions
    neg_pos = (~pos_this.astype('bool')).astype('float')
    # shift neg pos
    neg_pos_shift = neg_pos.shift().fillna(0)
    # Or neg pos with shifted neg pos
    final_neg_pos = ((neg_pos.astype('bool') | neg_pos_shift.astype('bool')).astype('float')).astype('float')

    # Calculate position price
    pos_avg_price = (final_neg_pos * price).replace(to_replace=0, method='ffill') * pos_this
    return pos_avg_price
# enddef

def positions_to_avg_position_price(pos, price, mode='any'):
    if mode == 'long':
        return __calc_avg_position_size_vec(pos, price, 'long')
    elif mode == 'short':
        return __calc_avg_position_size_vec(pos, price, 'short')
    else:
        return __calc_avg_position_size_vec(pos, price, 'long') + __calc_avg_position_size_vec(pos, price, 'short')
    # endif
# enddef
