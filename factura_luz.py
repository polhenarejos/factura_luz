#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Aug  2 00:12:18 2021

@author: polhenarejos
"""

import csv
import json
import requests
import os
import datetime

VERSION = '0.5.0.dev'

def get_esios(date):
    if (not os.path.exists('.cache/')):
        os.makedirs('.cache/')
    try:
        with open('.cache/'+date) as f:
            return json.load(f)
    except FileNotFoundError:
        r = requests.get('https://api.esios.ree.es/archives/70/download_json?locale=es&date='+date)
        j = r.json()
        with open('.cache/'+date,'w') as f:
            json.dump(j,f)
        return j

def get_price(dates,mode):
    prices = {}
    for date in dates:
        e = date.split('/')
        if (len(e) == 3):
            _mode = mode
            if (not _mode):
                if (datetime.date(int(e[2]),int(e[1]),int(e[0])) < datetime.date(2021,6,1)):
                    _mode = 'GEN'
                else:
                    _mode = 'PCB'
            pdate = '{}-{}-{}'.format(e[2],e[1],e[0])
            j = get_esios(pdate).get('PVPC',[])
            prices[date] = {}
            for h in j:
                hh = h['Hora'].split('-')
                prices[date].update({str(int(hh[1])): float(h[_mode].replace(',','.'))/1e3})
    return prices

def year_days(year):    
    return datetime.date(year,12,31).timetuple().tm_yday

def get_power_price(date,pw_punta,pw_valle=None):
    e = date.split('/')
    if (datetime.date(int(e[2]),int(e[1]),int(e[0])) < datetime.date(2021,6,1)):
        return (pw_punta * (38.043426+3.113)) / 365
    P1 = 30.67266
    P2 = 1.4243591
    PM = 3.113
    if (pw_valle is None):
        pw_valle = pw_punta
    return (pw_punta * P1 + pw_valle * P2 + pw_punta * PM) / 365

def get_iva(date):
    e = date.split('/')
    d = datetime.date(int(e[2]),int(e[1]),int(e[0]))
    if (datetime.date(2021,6,26) <= d <= datetime.date(2021,12,31)):
        return 0.1
    return 0.21
    

def parse_csv(file):
    bono_social = 0.25
    modo = None # 2.0TD PCB (Peninsula) y CYM (Ceuta y Melilla)
                 # GEN (2.0A, defecto), NOC (2.0DHA, 2 periodos), VHC (2.0DHS, 3 periodos)
    with open(file) as f:
        reader = csv.reader(f,delimiter=';')
        next(reader,None)
        dates = set([r[1] for r in reader])
        prices = get_price(dates, modo)
        price_kwh = 0
        f.seek(0)
        next(reader,None)
        for r in reader:
            hora = r[2]
            kwh = float(r[3].replace(',','.'))
            price = round(prices[r[1]][hora],6)
            price_kwh = price_kwh+price*kwh
        price_kwh = round(price_kwh,2)
        print('Precio kWh:', price_kwh)
        price_kw = 0
        iva = 0
        for date in dates:
            price_kw = price_kw+get_power_price(date,4.6)
            iva = iva+get_iva(date)
        price_kw = round(price_kw,2)
        print('Precio kW:', price_kw)
        descuento_bono = round(bono_social*(price_kw+price_kwh),2)
        if (descuento_bono > 0):
            print('Descuento bono social:',-descuento_bono)
        subtotal = round(price_kw+price_kwh-descuento_bono,2)
        print('Subtotal:',subtotal)
        imp_ele = round(0.0511269632 * subtotal,2)
        print('Impuesto electricidad:',imp_ele)
        alq_contador = round(9.72 * len(dates)/365,2)
        print('Alquiler contador:', alq_contador)
        total = round(subtotal+imp_ele+alq_contador,2)
        print('Total:',total)
        iva = iva/len(dates)
        iva_valor = round(iva*total,2)
        print('IVA ({}%): {}'.format(int(round(iva*100,0)),iva_valor))
        total_iva = round(total+iva_valor,2)
        print('TOTAL con IVA:',total_iva)

parse_csv('/Downloads/0682o00000LQ57x.csv')
