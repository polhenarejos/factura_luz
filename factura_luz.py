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
import logging
import time

VERSION = '0.8.1.dev'


logging.basicConfig(format='[%(asctime)s] [%(name)s::%(levelname)s] %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
logger = logging.getLogger('FacturaLuz')
logger.setLevel(logging.ERROR)

def get_esios(date):
    if (not os.path.exists('.cache/')):
        os.makedirs('.cache/')
        logger.info('La carpeta cache no existe. Creando.')
    try:
        with open('.cache/'+date) as f:
            logger.debug('Usando fecha {} en caché.'.format(date))
            return json.load(f)
    except FileNotFoundError:
        logger.info('La fecha no está en caché. Descargando los datos para el {}'.format(date))
        r = requests.get('https://api.esios.ree.es/archives/70/download_json?locale=es&date='+date)
        j = r.json()
        with open('.cache/'+date,'w') as f:
            json.dump(j,f)
        return j
    
def istd(date):
    e = date.split('/')
    if (len(e) == 3):
        return datetime.date(int(e[2]),int(e[1]),int(e[0])) >= datetime.date(2021,6,1)
    raise ValueError('Wrong date format ({})'.format(date))

def get_price(dates,mode):
    prices = {}
    for date in dates:
        e = date.split('/')
        if (len(e) == 3):
            _mode = mode
            if (((_mode == 'GEN' or _mode == 'NOC' or _mode == 'VHC') and istd(date)) or ((_mode == 'PCB' or _mode == 'CYM') and not istd(date))):
                logger.error('Modo {} seleccionado pero la tarifa {} es 2.0TD. Seleccionando {} por defecto.'.format(_mode,'no' if not istd else '','PCB' if istd else 'GEN'))
                _mode = None
            if (not _mode):
                if (not istd):
                    _mode = 'GEN'
                else:
                    _mode = 'PCB'
                logger.info('Seleccionando tarifa 2.0{} {} por defecto'.format('A' if _mode == 'GEN' else 'TD',_mode))
            pdate = '{}-{}-{}'.format(e[2],e[1],e[0])
            j = get_esios(pdate).get('PVPC',[])
            prices[date] = {}
            for h in j:
                hh = h['Hora'].split('-')
                prices[date].update({str(int(hh[1])): float(h[_mode].replace(',','.'))/1e3})
        else:
            logger.error('Fecha {} con formato incorrecto. Error no recuperable.'.format(date))
    return prices

def year_days(year):    
    return datetime.date(year,12,31).timetuple().tm_yday

def get_power_price(date,pw_punta,pw_valle=None):
    if (not istd(date)):
        logger.debug('Detectada potencia en tarifa 2.0A')
        return (pw_punta * (38.043426+3.113)) / 365
    logger.debug('Fecha {}: detectada potencia en tarifa 2.0TD'.format(date))
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
        logger.debug('Fecha {}: detectado IVA del 10%'.format(date))
        return 0.1
    logger.debug('Fecha {}: detectado IVA del 21%'.format(date))
    return 0.21

def es_festivo(date):
    festivos = ['1/1/21','6/1/21','2/4/21','1/5/21','12/10/21','1/11/21','6/12/21','8/12/21','25/12/21']
    return date in festivos
    
def es_valle(date):
    e = date.split('/')
    d = datetime.date(int(e[2]),int(e[1]),int(e[0]))
    return d.weekday() == 5 or d.weekday() == 6 or es_festivo(date)

def es_dst(date):
    e = date.split('/')
    d = datetime.date(int(e[2]),int(e[1]),int(e[0]))
    return time.localtime(d.timestamp()).tm_isdst == 1

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
        total_kwh = 0
        f.seek(0)
        next(reader,None)
        P1,P2,P3 = {},{},{}
        P1['kwh'],P2['kwh'],P3['kwh'] = 0,0,0
        P1['price'],P2['price'],P3['price'] = 0,0,0
        for r in reader:
            hora = r[2]
            kwh = float(r[3].replace(',','.'))
            price = round(prices[r[1]][hora],6)
            price_kwh = price_kwh+price*kwh
            total_kwh = total_kwh+kwh
            horai = int(hora)
            if (istd(r[1])):
                if (horai <= 8 or es_valle(r[1])):
                    P3['kwh'] = P3['kwh']+kwh
                    P3['price'] = P3['price']+price*kwh
                elif ((8 < horai <= 10 and not args.cym) or (8 < horai <= 11 and args.cym)  or (14 < horai <= 18 and not args.cym) or (14 < horai <= 19 and args.cym) or (22 < horai <= 24 and not args.cym) or (23 < horai <= 24 and args.cym)):
                    P2['kwh'] = P2['kwh']+kwh
                    P2['price'] = P2['price']+price*kwh
                elif ((10 < horai <= 14 and not args.cym) or (11 < horai <= 15 and args.cym) or (18 < horai <= 22 and not args.cym) or (19 < horai <= 23 and args.cym)):
                    P1['kwh'] = P1['kwh']+kwh
                    P1['price'] = P1['price']+price*kwh
            else:
                if (args.dha):
                    dst = es_dst(r[1])
                    if ((12 < horai <= 22 and not dst) or (13 < horai <= 23 and dst)):
                        P1['kwh'] = P1['kwh']+kwh
                        P1['price'] = P1['price']+price*kwh
                    else:
                        P1['kwh'] = P1['kwh']+kwh
                        P1['price'] = P1['price']+price*kwh
                elif (args.dhs):
                    if (13 < horai <= 23):
                        P1['kwh'] = P1['kwh']+kwh
                        P1['price'] = P1['price']+price*kwh
                    elif (7 < horai <= 13 or horai > 23 or horai <= 1):
                        P2['kwh'] = P2['kwh']+kwh
                        P2['price'] = P2['price']+price*kwh
                    elif (1 < horai <= 7):
                        P3['kwh'] = P3['kwh']+kwh
                        P3['price'] = P3['price']+price*kwh
                        
        price_kwh = round(price_kwh,2)
        print('Precio kWh:', price_kwh)
        if (P1['kwh'] and P2['kwh'] and P3['kwh']):
            print('\tConsumos por periodo: P1 (Punta): {} kWh ({}%), P2 (Llano): {} kWh ({}%), P3 (Valle): {} kWh ({}%)'.format(round(P1['kwh'],3),round(P1['kwh']/total_kwh*100,2),round(P2['kwh'],3),round(P2['kwh']/total_kwh*100,2),round(P3['kwh'],3),round(P3['kwh']/total_kwh*100,2)))
            print('\tPrecios por periodo: P1 (Punta): {} € ({}%), P2 (Llano): {} € ({}%), P3 (Valle): {} € ({}%)'.format(round(P1['price'],2),round(P1['price']/price_kwh*100,2),round(P2['price'],2),round(P2['price']/price_kwh*100,2),round(P3['price'],2),round(P3['price']/price_kwh*100,2)))
        elif (P1['kwh'] and P2['kwh']):
            print('\tConsumos por periodo: P1 (Punta): {} kWh ({}%), P2 (Punta): {} kWh ({}%)'.format(round(P1['kwh'],3),round(P1['kwh']/total_kwh*100,2),round(P2['kwh'],3),round(P2['kwh']/total_kwh*100,2)))
            print('\tPrecios por periodo: P1 (Punta): {} € ({}%), P2 (Punta): {} € ({}%)'.format(round(P1['price'],2),round(P1['price']/price_kwh*100,2),round(P2['price'],2),round(P2['price']/price_kwh*100,2)))
        else:
            print('\tConsumos por periodo: P1: {} kWh ({}%)'.format(round(P1['kwh'],3),round(P1['kwh']/total_kwh*100,2)))
            print('\tPrecios por periodo: P1: {} € ({}%)'.format(round(P1['price'],2),round(P1['price']/price_kwh*100,2)))
        print('\tTotal consumo: {} kWh'.format(round(total_kwh)))
        price_kw = 0
        iva = 0
        for date in dates:
            price_kw = price_kw+get_power_price(date,pw_punta=float(args.potencia),pw_valle=float(args.valle) if args.valle else None)
            iva = iva+get_iva(date)
        price_kw = round(price_kw,2)
        print('Precio kW:', price_kw)
        descuento_bono = 0
        if (bono_social > 0):
            days = len(dates)
            limite = 1380
            if (args.bono1):
                limite = 1932
            elif (args.bono2):
                limite = 2346
            elif (args.bono3):
                limite = 4140
            limite = limite*days/365
            factor = min(1,limite/total_kwh)
            descuento_bono = round(bono_social*(price_kw+factor*price_kwh),2)
            if (descuento_bono > 0):
                print('Descuento bono social:',-descuento_bono)
                print('Limite de descuento: {}%'.format(round(factor*100,2)))
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
    logger.debug('patata')
    main(args)
