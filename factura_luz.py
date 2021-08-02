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
import argparse

VERSION = '0.6.0.dev'

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
    

def parse_csv(args):
    bono_social = 0
    if (args.bono0 or args.bono1 or args.bono2 or args.bono3):
        bono_social = 0.4 if args.severo else 0.25
    modo = None # 2.0TD PCB (Peninsula) y CYM (Ceuta y Melilla)
                 # GEN (2.0A, defecto), NOC (2.0DHA, 2 periodos), VHC (2.0DHS, 3 periodos)
    if (args.dha):
        modo = 'NOC'
    elif (args.dhs):
        modo = 'VHC'
    elif (args.cym):
        modo = 'CYM'
    with open(args.file) as f:
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
            price_kw = price_kw+get_power_price(date,pw_punta=float(args.potencia),pw_valle=float(args.valle) if args.valle else None)
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
        
def main(args):
    parse_csv(args)

def parse_args():
    parser = argparse.ArgumentParser(description='Simulador de la factura de la luz de España según mercado regulado')
    parser.add_argument('-f', '--file', help='Archivo CSV de los consumos facilitado por la distribuidora', required=True)
    parser.add_argument('-p', '--potencia', help='Potencia (en kW). En tarificación 2.0TD corresponde a la potencia punta', required=True)
    parser.add_argument('-v', '--valle', help='Potencia valle (en kW) en tarificación 2.0TD. Si no se especifica se utiliza el valor de potencia punta')
    parser.add_argument('-c', '--cym', help='Residente de Ceuta y Melilla (para 2.0TD)', action='store_true')
    parser.add_argument('-d', '--dha', help='Tarificación en 2 periodos (para 2.0DHA)', action='store_true')
    parser.add_argument('-s', '--dhs', help='Tarificación en 3 periodos (para 2.0DHS)', action='store_true')
    parser.add_argument('-0', '--bono0', help='Bono social tipo 0 (sin menores / individual)', action='store_true')
    parser.add_argument('-1', '--bono1', help='Bono social tipo 1 (1 menor / pensionista mínimo)', action='store_true')
    parser.add_argument('-2', '--bono2', help='Bono social tipo 2 (2 menores)', action='store_true')
    parser.add_argument('-3', '--bono3', help='Bono social tipo 3 (familia numerosa)', action='store_true')
    parser.add_argument('-S', '--severo', help='Bono social de consumidor vulnerable severo', action='store_true')
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_args()
    main(args)
