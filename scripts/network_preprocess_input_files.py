import time
start = time.time()
import os
import sys
from pprint import pprint
import configparser
import csv
import fiona
import numpy as np
import random
import glob

from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon, mapping, MultiPoint
from shapely.ops import unary_union, cascaded_union
from pyproj import Proj, transform
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from scipy.spatial import Voronoi, voronoi_plot_2d
from rtree import index
from operator import itemgetter

from collections import OrderedDict, defaultdict

import osmnx as ox, networkx as nx

CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(os.path.dirname(__file__), 'script_config.ini'))
BASE_PATH = CONFIG['file_locations']['base_path']

# set timesteps
BASE_YEAR = 2018
END_YEAR = 2018
TIMESTEP_INCREMENT = 1
TIMESTEPS = range(BASE_YEAR, END_YEAR + 1, TIMESTEP_INCREMENT)

#####################################
# setup file locations and data files
#####################################

# DATA_RAW = os.path.join(BASE_PATH, 'raw')
# DATA_INTERMEDIATE = os.path.join(BASE_PATH, 'intermediate')
# SYSTEM_INPUT_NETWORK = os.path.join(DATA_RAW, 'network_hierarchy_data')

#####################################
# setup test data file locations 
#####################################

DATA_RAW = os.path.join(BASE_PATH, 'network_generation_test_data_cambridgeshire', 'raw')
DATA_INTERMEDIATE = os.path.join(BASE_PATH, 'network_generation_test_data_cambridgeshire', 'intermediate')
SYSTEM_INPUT_NETWORK = os.path.join(DATA_RAW, 'network_hierarchy_data')

#####################################
# READ EXCHANGE AREA
#####################################

def read_exchange_area(exchange_name):
    with fiona.open(os.path.join(DATA_INTERMEDIATE, '_exchange_areas.shp'), 'r') as source:
        return [exchange for exchange in source if exchange['properties']['id'] == exchange_name][0]

def read_lads(exchange_area):
    with fiona.open(os.path.join(DATA_RAW, 'lad_uk_2016-12', 'lad_uk_2016-12.shp'), 'r') as source:
        exchange_geom = shape(exchange_area['geometry'])
        return [lad for lad in source if exchange_geom.intersection(shape(lad['geometry']))]

def get_lad_area_ids(lad_areas):
    lad_area_ids = []
    for lad in lad_areas:
        lad_area_ids.append(lad['properties']['name'])
    return lad_area_ids

#####################################
# INTEGRATE WTP AND WTA HOUSEHOLD DATA INTO PREMIses
#####################################

def read_msoa_data(lad_ids):
    """
    MSOA data contains individual level demographic characteristics including:
        - PID - Person ID
        - MSOA - Area ID
        - DC1117EW_C_SEX - Gender
        - DC1117EW_C_AGE - Age
        - DC2101EW_C_ETHPUK11 - Ethnicity
        - HID - Household ID
        - year - year
    """
    
    MSOA_data = []

    msoa_lad_id_files = {
        lad: os.path.join(DATA_RAW,'demographic_scenario_data','msoa_2018','ass_{}_MSOA11_2018.csv'.format(lad))
        for lad in lad_ids
    }

    pathlist = glob.iglob(os.path.join(DATA_RAW, 'demographic_scenario_data','msoa_2018') + '/*.csv', recursive=True)

    for filename in msoa_lad_id_files.values():
        with open(os.path.join(filename), 'r') as system_file:
            year_reader = csv.reader(system_file)
            next(year_reader, None)
            # Put the values in the population dict
            for line in year_reader:
                MSOA_data.append({
                    'PID': line[0],
                    'MSOA': line[1],
                    'lad': filename[-25:-16],
                    'gender': line[2],
                    'age': line[3],
                    'ethnicity': line[4],
                    'HID': line[5],
                    'year': int(filename[-8:-4]),
                })     

    return MSOA_data

def read_age_data():
    """
    Contains data on fixed broadband adoption by age :
        - Age 
        - % chance of adopt
    """
    my_data = []

    with open(os.path.join(BASE_PATH, 'raw', 'willingness_to_pay', 'age.csv'), 'r') as my_file:
        reader = csv.reader(my_file)
        next(reader, None)
        for row in reader:
            my_data.append({
                'age': row[0],
                'age_wta': int(row[1])
            })

        return my_data

def read_gender_data():
    """
    Contains data on fixed broadband adoption by socio-economic status (ses):
        - ses
        - % chance of adopt
    """
    my_data = []

    with open(os.path.join(BASE_PATH, 'raw', 'willingness_to_pay', 'gender.csv'), 'r') as my_file:
        reader = csv.reader(my_file)
        next(reader, None)
        for row in reader:
            my_data.append({
                'gender': row[0],
                'gender_wta': int(row[1])
            })

        return my_data

def read_nation_data():
    """
    Contains data on fixed broadband adoption by nation:
        - nation
        - % chance of adopt
    """
    my_data = []

    with open(os.path.join(BASE_PATH, 'raw', 'willingness_to_pay', 'nation.csv'), 'r') as my_file:
        reader = csv.reader(my_file)
        next(reader, None)
        for row in reader:
            my_data.append({
                'nation': row[0],
                'nation_wta': int(row[1])
            })

        return my_data

def read_urban_rural_data():
    """
    Contains data on fixed broadband adoption by urban_rural:
        - urban_rural
        - % chance of adopt
    """
    my_data = []

    with open(os.path.join(BASE_PATH, 'raw', 'willingness_to_pay', 'urban_rural.csv'), 'r') as my_file:
        reader = csv.reader(my_file)
        next(reader, None)
        for row in reader:
            my_data.append({
                'urban_rural': row[0],
                'urban_rural_wta': int(row[1])
            })

        return my_data

def add_country_indicator(data):

    for person in data:

        if person['lad'].startswith("E"):
            person['nation'] = 'england'
        if person['lad'].startswith("S"):
            person['nation'] = 'scotland'
        if person['lad'].startswith("w"):
            person['nation'] = 'wales'
        if person['lad'].startswith("N"):
            person['nation'] = 'northern ireland'

    return data

def read_ses_data():
    """
    Contains data on fixed broadband adoption by socio-economic status (ses):
        - ses
        - % chance of adopt
    """
    my_data = []

    with open(os.path.join(BASE_PATH, 'raw', 'willingness_to_pay', 'ses.csv'), 'r') as my_file:
        reader = csv.reader(my_file)
        next(reader, None)
        for row in reader:
            my_data.append({
                'ses': row[0],
                'ses_wta': int(row[1])
            })

        return my_data

def add_data_to_MSOA_data(consumer_data, population_data, variable):
    """
    Take the WTP lookup table for all ages. Add to the population data based on age.
    """
    d1 = {d[variable]:d for d in consumer_data}

    population_data = [dict(d, **d1.get(d[variable], {})) for d in population_data]	

    return population_data

def read_oa_data():
    """
    MSOA data contains individual level demographic characteristics including:
        - HID - Household ID
        - OA - Output Area ID
        - ses - Household Socio-Economic Status
        - year - year
    """
    
    OA_data = []

    oa_lad_id_files = {
        lad: os.path.join(DATA_RAW, 'demographic_scenario_data','oa_2018','ass_hh_{}_OA11_2018.csv'.format(lad))
        for lad in lad_ids
    }

    for filename in oa_lad_id_files.values():
        # Open file
        with open(filename, 'r') as year_file:
            year_reader = csv.reader(year_file)
            next(year_reader, None)
            # Put the values in the population dict
            for line in year_reader:
                OA_data.append({
                    'HID': line[0],
                    'OA': line[1],
                    'lad': filename[-23:-14],
                    'ses': line[12],
                    'year': int(filename[-8:-4]),
                })     

    return OA_data

def convert_ses_grades(data):

    for household in data:
        if household['ses'] == '1':
            household['ses'] = 'AB'
        elif household['ses'] == '2':
            household['ses'] = 'AB'
        elif household['ses'] == '3':
            household['ses'] = 'C1'
        elif household['ses'] == '4':
            household['ses'] = 'C1'
        elif household['ses'] == '5':
            household['ses'] = 'C2'
        elif household['ses'] == '6':
            household['ses'] = 'DE'
        elif household['ses'] == '7':
            household['ses'] = 'DE'
        elif household['ses'] == '8':
            household['ses'] = 'DE'
        elif household['ses'] == '9':
            household['ses'] = 'students'
    
    return data

def merge_two_lists_of_dicts(msoa_list_of_dicts, oa_list_of_dicts, parameter1, parameter2, parameter3):
    """
    Combine the msoa and oa dicts using the household indicator and year keys. 
    """
    d1 = {(d[parameter1], d[parameter2], d[parameter3]):d for d in oa_list_of_dicts}

    msoa_list_of_dicts = [dict(d, **d1.get((d[parameter1], d[parameter2], d[parameter3]), {})) for d in msoa_list_of_dicts]	

    return msoa_list_of_dicts

def get_missing_ses_key(data):

    complete_data = []
    missing_ses = []

    for prem in data:
        if 'ses' in prem and 'ses_wta' in prem:
            complete_data.append({
                'PID': prem['PID'],
                'MSOA': prem['MSOA'],
                'lad': prem['lad'],
                'gender': prem['gender'],
                'age': prem['age'],
                'ethnicity': prem['ethnicity'],
                'HID': prem['HID'],
                'year': prem['year'],
                'nation': prem['nation'],
                'age_wta': prem['age_wta'],
                'gender_wta': prem['gender_wta'],
                'OA': prem['OA'],
                'ses': prem['ses'],
                'ses_wta': prem['ses_wta'],
            })
        else:
            missing_ses.append({
                'PID': prem['PID'],
                'MSOA': prem['MSOA'],
                'lad': prem['lad'],
                'gender': prem['gender'],
                'age': prem['age'],
                'ethnicity': prem['ethnicity'],
                'HID': prem['HID'],
                'year': prem['year'],
                'nation': prem['nation']
            })

    return complete_data, missing_ses

def calculate_adoption_propensity(data):

    for person in data:
        person['wta'] = person['age_wta'] * person['gender_wta'] * person['ses_wta'] 

    return data

def calculate_wtp(data):

    for person in data:
        person['wta'] = person['age_wta'] * person['gender_wta'] * person['ses_wta'] 

        if person['wta'] < 1800000:
            person['wtp'] = 20
        elif person['wta'] > 1800000 and  person['wta'] < 2200000:
            person['wtp'] = 30
        elif person['wta'] > 2200000 and  person['wta'] < 2600000:
            person['wtp'] = 40
        elif person['wta'] > 2600000 and  person['wta'] < 3000000:
            person['wtp'] = 50
        elif person['wta'] > 3000000:
            person['wtp'] = 60
    return data


def aggregate_wtp_and_wta_by_household(data):
    """
    Aggregate wtp by household by Household ID (HID), Local Authority District (lad) and year.
    """
    d = defaultdict(lambda: defaultdict(int))

    group_keys = ['HID','lad', 'year']
    sum_keys = ['wta','wtp']

    for item in data:
        for key in sum_keys:
            d[itemgetter(*group_keys)(item)][key] += item[key]

    results = [{**dict(zip(group_keys, k)), **v} for k, v in d.items()]

    return results

def read_premises_data(exchange_area):
    """
    Reads in premises points from the OS AddressBase data (.csv).

    Data Schema
    ----------
    * id: :obj:`int`
        Unique Premises ID
    * oa: :obj:`str`
        ONS output area code
    * residential address count: obj:'str'
        Number of residential addresses
    * non-res address count: obj:'str'
        Number of non-residential addresses
    * postgis geom: obj:'str'
        Postgis reference
    * E: obj:'float'
        Easting coordinate
    * N: obj:'float'
        Northing coordinate

    """
    premises_data = []

    pathlist = glob.iglob(os.path.join(DATA_RAW, 'layer_5_premises', 'blds_with_functions_EO_2018_03_29') + '/*.csv', recursive=True)

    exchange_geom = shape(exchange_area['geometry'])
    exchange_bounds = shape(exchange_area['geometry']).bounds

    for path in pathlist:
        with open(os.path.join(path), 'r') as system_file:
            reader = csv.reader(system_file)
            next(reader)
            [premises_data.append({
                'uid': line[0],
                'oa': line[1],
                'gor': line[2],
                'residential_address_count': line[3],
                'non_residential_address_count': line[4],
                'function': line[5],
                'postgis_geom': line[6],
                'N': line[7],
                'E':line[8],
            }) 
                for line in reader
                if (exchange_bounds[0] <= float(line[8]) and exchange_bounds[1] <= float(line[7]) and exchange_bounds[2] >= float(line[8]) and exchange_bounds[3] >= float(line[7]))
            ]
  
    # remove 'None' and replace with '0'
    for idx, row in enumerate(premises_data):
        if row['residential_address_count'] == 'None':
            premises_data[idx]['residential_address_count'] = '0'
        if row['non_residential_address_count'] == 'None':
            premises_data[idx]['non_residential_address_count'] = '0'

    for row in premises_data:
        row['residential_address_count']  = int(row['residential_address_count'])

    return premises_data

def expand_premises(pemises_data):
    """
    Take a single address with multiple units, and expand to get a dict for each unit.
    """
    processed_pemises_data = [] 

    [processed_pemises_data.extend([entry]*entry['residential_address_count']) for entry in pemises_data]

    return processed_pemises_data

def merge_prems_and_housholds(premises_data, household_data):
    """
    Merges two aligned datasets, zipping row to row. 
    Deals with premises_data having multiple repeated dict references due to expand function.
    """
    result = [a.copy() for a in premises_data]

    [a.update(b) for a, b in zip(result, household_data)]

    return result

#####################################
# READ LOOK UP TABLE (LUT) DATA
#####################################

def read_pcd_to_exchange_lut():
    """
    Produces all unique postcode-to-exchange combinations from available data, including:

    'January 2013 PCP to Postcode File Part One.csv'
    'January 2013 PCP to Postcode File Part Two.csv'
    'pcp.to.pcd.dec.11.one.csv'
    'pcp.to.pcd.dec.11.two.csv'
    'from_tomasso_valletti.csv'

    Data Schema
    ----------
    * exchange_id: 'string'
        Unique Exchange ID
    * postcode: 'string'
        Unique Postcode 

    Returns
    -------
    pcd_to_exchange_data: List of dicts
    """
    pcd_to_exchange_data = []
    exchange_id =  exchange_name.replace('exchange_', '')

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'January 2013 PCP to Postcode File Part One.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'January 2013 PCP to Postcode File Part Two.csv'), 'r',  encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'pcp.to.pcd.dec.11.one.csv'), 'r',  encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'pcp.to.pcd.dec.11.two.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'from_tomasso_valletti.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    ### find unique values in list of dicts
    return list({pcd['postcode']:pcd for pcd in pcd_to_exchange_data}.values())

def read_pcd_to_cabinet_lut():
    """
    Produces all postcode-to-cabinet-to-exchange combinations from available data, including:

        - January 2013 PCP to Postcode File Part One.csv
        - January 2013 PCP to Postcode File Part Two.csv
        - pcp.to.pcd.dec.11.one.csv'
        - pcp.to.pcd.dec.11.two.csv'

    Data Schema
    -----------
    * exchange_id: 'string'
        Unique Exchange ID
    * name: 'string'
        Unique Exchange Name    
    * cabinet_id: 'string'
        Unique Cabinet ID
    * exchange_only_flag: 'int' 
        Exchange only binary
    
    Returns
    -------
    pcp_data: Dict of dicts
    """

    pcp_data = {}
    exchange_id =  exchange_name.replace('exchange_', '')


    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'January 2013 PCP to Postcode File Part One.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            if line[0] == exchange_id:
                pcp_data[line[2].replace(" ", "")] = {
                    'exchange_id': line[0],
                    'name': line[1],
                    'cabinet_id': line[3],
                    'exchange_only_flag': line[4]
                }

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'January 2013 PCP to Postcode File Part Two.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            if line[0] == exchange_id:
                pcp_data[line[2].replace(" ", "")] = {
                    'exchange_id': line[0],
                    'name': line[1],
                    'cabinet_id': line[3],
                    'exchange_only_flag': line[4]
                    ###skip other unwanted variables
                }

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'pcp.to.pcd.dec.11.one.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)
        for line in reader:
            if line[0] == exchange_id:
                pcp_data[line[2].replace(" ", "")] = {
                    'exchange_id': line[0],
                    'name': line[1],
                    'cabinet_id': line[3],
                    'exchange_only_flag': line[4]
                    ###skip other unwanted variables
                }

    with open(os.path.join(SYSTEM_INPUT_NETWORK, 'pcp.to.pcd.dec.11.two.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)
        for line in reader:
            if line[0] == exchange_id:
                pcp_data[line[2].replace(" ", "")] = {
                    'exchange_id': line[0],
                    'name': line[1],
                    'cabinet_id': line[3],
                    'exchange_only_flag': line[4]
                    ###skip other unwanted variables
                }


    return pcp_data

def read_postcode_areas(exchange_area):
    
    """
    Reads all postcodes shapes, removing vertical postcodes, and merging with closest neighbour.

    Data Schema
    -----------
    * POSTCODE: 'string'
        Unique Postcode

    Returns
    -------
    postcode_areas = list of dicts
    """
    exchange_geom = shape(exchange_area['geometry'])

    with fiona.open(os.path.join(DATA_INTERMEDIATE, '_postcode_areas.shp'), 'r') as source:
        return [postcode_area for postcode_area in source if exchange_geom.contains(shape(postcode_area['geometry']))]

def read_postcode_technology_lut():

    SYSTEM_INPUT_NETWORK = os.path.join(DATA_RAW, 'offcom_initial_system', 'fixed-postcode-2017')

    postcode_technology_lut = []
    for filename in os.listdir(SYSTEM_INPUT_NETWORK):
        with open(os.path.join(SYSTEM_INPUT_NETWORK, filename), 'r', encoding='utf8', errors='replace') as system_file:
            reader = csv.reader(system_file)
            next(reader)    
            for line in reader:
                postcode_technology_lut.append({
                    'postcode': line[0],
                    'sfbb_availability': line[3],
                    'ufbb_availability': line[4],
                    'fttp_availability': line[36],
                    'max_download_speed': line[12],
                    'max_upload_speed': line[20],
                    'average_data_download_adsl': line[33],
                    'average_data_download_sfbb': line[34],
                    'average_data_download_ufbb': line[35],                   
                })

    return postcode_technology_lut

def read_city_exchange_geotype_lut():

    exchange_geotypes = []
    with open(os.path.join(DATA_RAW, 'exchange_geotype_lut', 'exchange_geotype_lut.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)    
        for line in reader:
            exchange_geotypes.append({
                'lad': line[0],
                'geotype': line[1],                
            })

    return exchange_geotypes

#####################################
# READ PREMIses/ASSETS
#####################################

def read_premises(exchange_area, exchange_abbr):

    """
    Reads in premises points from the OS AddressBase data (.csv).

    Data Schema
    ----------
    * id: :obj:`int`
        Unique Premises ID
    * oa: :obj:`str`
        ONS output area code
    * residential address count: obj:'str'
        Number of residential addresses
    * non-res address count: obj:'str'
        Number of non-residential addresses
    * postgis geom: obj:'str'
        Postgis reference
    * E: obj:'float'
        Easting coordinate
    * N: obj:'float'
        Northing coordinate

    Returns
    -------
    array: with GeoJSON dicts containing shapes and attributes
    """

    premises_data = []
    idx = index.Index()

    #pathlist = glob.iglob(os.path.join(DATA_INTERMEDIATE) + '/*.csv', recursive=True)

    exchange_geom = shape(exchange_area['geometry'])
    exchange_bounds = shape(exchange_area['geometry']).bounds

    #for path in pathlist:
    with open(os.path.join(DATA_INTERMEDIATE, '{}_premises_data.csv'.format(exchange_abbr)), 'r') as system_file:
        reader = csv.reader(system_file)
        next(reader) #skip header
        [premises_data.append(
            {
                'type': "Feature",
                'geometry': {
                    "type": "Point",
                    "coordinates": [float(line[8]), float(line[7])]
                },
                'properties': {
                    'id': 'premise_' + line[0],
                    'oa': line[1],
                    'residential_address_count': line[3],
                    'non_residential_address_count': line[4],
                    'function': line[5],
                    'postgis_geom': line[6],
                    'HID': line[9],
                    'lad': line[10],
                    'year': line[11],
                    'wta': line[12],
                    'wtp': line[13],
                }
            }) 
            for line in reader
            if (exchange_bounds[0] <= float(line[8]) and exchange_bounds[1] <= float(line[7]) and exchange_bounds[2] >= float(line[8]) and exchange_bounds[3] >= float(line[7]))
        ]

    premises_data = [premise for premise in premises_data if exchange_geom.contains(shape(premise['geometry']))]

    # remove 'None' and replace with '0'
    for idx, premise in enumerate(premises_data):
        if premise['properties']['residential_address_count'] == 'None':
            premises_data[idx]['properties']['residential_address_count'] = '0'
        if premise['properties']['non_residential_address_count'] == 'None':
            premises_data[idx]['properties']['non_residential_address_count'] = '0'

    return premises_data

def read_exchanges(exchange_area):

    """
    Reads in exchanges from 'final_exchange_pcds.csv'. 

    Data Schema
    ----------
    * id: 'string'
        Unique Exchange ID
    * Name: 'string'
        Unique Exchange Name
    * pcd: 'string'
        Unique Postcode
    * Region: 'string'
        Region ID
    * County: 'string'
        County IS
    
    Returns
    -------
    exchanges: List of dicts
    """

    idx = index.Index()

    with open(os.path.join(DATA_RAW, 'layer_2_exchanges', 'final_exchange_pcds.csv'), 'r') as system_file:
        reader = csv.reader(system_file)
        next(reader)
    
        [idx.insert(0, 
            (
                float(line[5]), 
                float(line[6]), 
                float(line[5]), 
                float(line[6]), 
            ),
            {
                'type': "Feature",
                'geometry': {
                    "type": "Point",
                    "coordinates": [float(line[5]), float(line[6])]
                },
                'properties': {
                    'id': 'exchange_' + line[1],
                    'Name': line[2],
                    'pcd': line[0],
                    'Region': line[3],
                    'County': line[4]
                }
            }) 
            for line in reader
        ]

    exchange_geom = shape(exchange_area['geometry'])
    return [n.object for n in idx.intersection(shape(exchange_area['geometry']).bounds, objects=True) if exchange_geom.intersection(shape(n.object['geometry']))]

#####################################
# PROCESS NETWORK HIERARCHY
#####################################

def add_exchange_id_to_postcode_areas(exchanges, postcode_areas, exchange_to_postcode):

    """
    Either uses known data or estimates which exchange each postcode is likely attached to.

    Arguments
    ---------

    * exchanges: 'list of dicts'
        List of Exchanges from read_exchanges()
    * postcode_areas: 'list of dicts'
        List of Postcode Areas from read_postcode_areas()
    * exchange_to_postcode: 'list of dicts'
        List of Postcode to Exchange data procudes from read_pcd_to_exchange_lut()
    
    Returns
    -------
    postcode_areas: 'list of dicts'    
    """
    idx_exchanges = index.Index()
    lut_exchanges = {}

    # Read the exchange points
    for idx, exchange in enumerate(exchanges):

        # Add to Rtree and lookup table
        idx_exchanges.insert(idx, tuple(map(int, exchange['geometry']['coordinates'])) + tuple(map(int, exchange['geometry']['coordinates'])), exchange['properties']['id'])
        lut_exchanges[exchange['properties']['id']] = {
            'Name': exchange['properties']['Name'],
            'pcd': exchange['properties']['pcd'].replace(" ", ""),
            'Region': exchange['properties']['Region'],
            'County': exchange['properties']['County'],
        }

    # Read the postcode-to-cabinet-to-exchange lookup file
    lut_pcb2cab = {}

    for idx, row in enumerate(exchange_to_postcode):
        lut_pcb2cab[row['postcode']] = row['exchange_id']

    # Connect each postcode area to an exchange
    for postcode_area in postcode_areas:

        postcode = postcode_area['properties']['POSTCODE']

        if postcode in lut_pcb2cab:

            # Postcode-to-cabinet-to-exchange association
            postcode_area['properties']['EX_ID'] = 'exchange_' + lut_pcb2cab[postcode]
            postcode_area['properties']['EX_SRC'] = 'EXISTING POSTCODE DATA'

        else:

            # Find nearest exchange
            nearest = [n.object for n in idx_exchanges.nearest((shape(postcode_area['geometry']).bounds), 1, objects=True)]
            postcode_area['properties']['EX_ID'] = nearest[0]
            postcode_area['properties']['EX_SRC'] = 'ESTIMATED NEAREST'

        # Match the exchange ID with remaining exchange info
        if postcode_area['properties']['EX_ID'] in lut_exchanges:
            postcode_area['properties']['EX_NAME'] = lut_exchanges[postcode_area['properties']['EX_ID']]['Name']
            postcode_area['properties']['EX_PCD'] = lut_exchanges[postcode_area['properties']['EX_ID']]['pcd']
            postcode_area['properties']['EX_REGION'] = lut_exchanges[postcode_area['properties']['EX_ID']]['Region']
            postcode_area['properties']['EX_COUNTY'] = lut_exchanges[postcode_area['properties']['EX_ID']]['County']
        else:
            postcode_area['properties']['EX_NAME'] = ""
            postcode_area['properties']['EX_PCD'] = ""
            postcode_area['properties']['EX_REGION'] = ""
            postcode_area['properties']['EX_COUNTY'] = ""

    return postcode_areas

def add_cabinet_id_to_postcode_areas(postcode_areas, pcd_to_cabinet):
    
    for postcode_area in postcode_areas:
        if postcode_area['properties']['POSTCODE'] in pcd_to_cabinet:
            postcode_area['properties']['CAB_ID'] = pcd_to_cabinet[postcode_area['properties']['POSTCODE']]['cabinet_id']
        else:
            postcode_area['properties']['CAB_ID'] = ""
    
    return postcode_areas

def add_postcode_to_premises(premises, postcode_areas):

    joined_premises = []

    # Initialze Rtree
    idx = index.Index()
    [idx.insert(0, shape(premise['geometry']).bounds, premise) for premise in premises]

    # Join the two
    for postcode_area in postcode_areas:
        for n in idx.intersection((shape(postcode_area['geometry']).bounds), objects=True):
            postcode_area_shape = shape(postcode_area['geometry'])
            premise_shape = shape(n.object['geometry'])
            if postcode_area_shape.contains(premise_shape):
                n.object['properties']['postcode'] = postcode_area['properties']['POSTCODE']
                n.object['properties']['CAB_ID'] = postcode_area['properties']['CAB_ID']
                joined_premises.append(n.object)

    return joined_premises


def add_lad_to_matching_area(premises, lads):
    
    joined_premises = []

    # Initialze Rtree
    idx = index.Index()

    for rtree_idx, premise in enumerate(premises):
        idx.insert(rtree_idx, shape(premise['geometry']).bounds, premise)

    # Join the two
    for lad in lads:
        for n in idx.intersection((shape(lad['geometry']).bounds), objects=True):
            lad_shape = shape(lad['geometry'])
            premise_shape = shape(n.object['geometry'])
            if lad_shape.contains(premise_shape):
                n.object['properties']['lad'] = lad['properties']['name']
                joined_premises.append(n.object)

    return joined_premises

def add_lad_to_exchanges(exchanges, lads):
    
    joined_exchanges = []

    # Initialze Rtree
    idx = index.Index()

    for rtree_idx, exchange in enumerate(exchanges):
        idx.insert(rtree_idx, shape(exchange['geometry']).bounds, exchange)

    # Join the two
    for lad in lads:
        for n in idx.intersection((shape(lad['geometry']).bounds), objects=True):
            lad_shape = shape(lad['geometry'])
            premise_shape = shape(n.object['geometry'])
            if lad_shape.contains(premise_shape):
                n.object['properties']['lad'] = lad['properties']['name']
                joined_exchanges.append(n.object)

    return joined_exchanges

def add_urban_geotype_to_exchanges(exchanges, exchange_geotype_lut):

    # Process lookup into dictionary
    exchange_geotypes = {}
    for lad in exchange_geotype_lut:
        exchange_geotypes[lad['lad']] = lad
        del exchange_geotypes[lad['lad']]['lad']

    # Add properties
    for exchange in exchanges:
        if exchange['properties']['lad'] in exchange_geotypes:
            exchange['properties'].update({
                'geotype': exchange_geotypes[exchange['properties']['lad']]['geotype'],

            })
        else:
            exchange['properties'].update({
                'geotype': 'other', 
            })
    
    return exchanges

#####################################
# PROCESS ASSETS
#####################################

def complement_postcode_cabinets(postcode_areas, premises, exchanges, exchange_abbr):

    for exchange in exchanges:

        # Count number of existing cabinets
        cabinets_in_data = [postcode_area['properties']['CAB_ID'] for postcode_area in postcode_areas]
        count_cabinets_in_data = len(set(cabinets_in_data))
        
        # Calculate number of expected cabinets
        if exchange['properties']['geotype'] == 'large city': #>500k
            local_cluster_radius = 500
            minimum_samples = 500
        elif exchange['properties']['geotype'] == 'small city': #>200k
            local_cluster_radius = 500
            minimum_samples = 500
        elif exchange['properties']['geotype'] == '>20k lines':
            local_cluster_radius = 475
            minimum_samples = 200
        elif exchange['properties']['geotype'] == '>10k lines':
            local_cluster_radius = 400
            minimum_samples = 100
        elif exchange['properties']['geotype'] == '>3k lines':
            local_cluster_radius = 205
            minimum_samples = 75
        elif exchange['properties']['geotype'] == '>1k lines':
            local_cluster_radius = 185
            minimum_samples = 50
        elif exchange['properties']['geotype'] == '<1k lines' or 'other':
            local_cluster_radius = 100 # TODO: according to table these premises geotypes have no internet access
            minimum_samples = 25
        else:
            print('Geotype ' + exchange['properties']['geotype'] + ' is unknown')   
            raise Exception()

        points = np.vstack([[float(i) for i in premise['geometry']['coordinates']] for premise in premises])

        db = DBSCAN(eps=local_cluster_radius, min_samples=minimum_samples).fit(points)
        core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
        core_samples_mask[db.core_sample_indices_] = True
        labels = db.labels_
        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)
        clusters = [points[labels == i] for i in range(n_clusters_)]
        
        cabinets = []
        for idx, cluster in enumerate(clusters):
            cabinet_premises_geom = MultiPoint(cluster)
            cabinet_rep_point = cabinet_premises_geom.representative_point()
            cabinets.append({
                    'type': "Feature",
                    'geometry': {
                        "type": "Point",
                        "coordinates": [cabinet_rep_point.x, cabinet_rep_point.y]
                    },
                    'properties': {
                        "id": "{" + exchange_abbr + "}{GEN" + str(idx) + '}'
                    }
                })

    return cabinets

def allocate_to_cabinet(data, cabinets):

    cabinets_idx = index.Index()
    [cabinets_idx.insert(0, shape(cabinet['geometry']).bounds, obj=cabinet['properties']['id']) for cabinet in cabinets]

    for datum in data:
        if datum['properties']['CAB_ID'] == '':
            datum['properties']['CAB_ID'] = [n.object for n in cabinets_idx.nearest(shape(datum['geometry']).bounds, objects=True)][0]

    return data

def estimate_cabinet_locations(premises):
    '''
    Put a cabinet in the representative center of the set of premises served by it
    '''
    cabinet_by_id_lut = defaultdict(list)

    for premise in premises:
        cabinet_by_id_lut[premise['properties']['CAB_ID']].append(shape(premise['geometry']))
    
    cabinets = []
    for cabinet_id in cabinet_by_id_lut:
        if cabinet_id != "": 
            cabinet_premises_geom = MultiPoint(cabinet_by_id_lut[cabinet_id])

            cabinets.append({
                'type': "Feature",
                'geometry': mapping(cabinet_premises_geom.representative_point()),
                'properties': {
                    'id': 'cabinet_' + cabinet_id
                }
            })
    
    return cabinets

def estimate_dist_points(premises, exchange_name, cachefile=None):
    """Estimate distribution point locations.

    Parameters
    ----------
    cabinets: list of dict
        List of cabinets, each providing a dict with properties and location of the cabinet

    Returns
    -------
    dist_point: list of dict
                List of dist_points
    """
    dist_points = []

    # Use previous file if specified
    if cachefile != None:
        cachefile = os.path.join(DATA_INTERMEDIATE, cachefile)
        if os.path.isfile(cachefile):
            with fiona.open(cachefile, 'r') as source:
                for f in source:
                    # Make sure additional properties are not copied
                    dist_points.append({
                        'type': "Feature",
                        'geometry': f['geometry'],
                        'properties': {
                            "id": f['properties']['id']
                        }
                    })       
                return dist_points

    # Generate points
    points = np.vstack([[float(i) for i in premise['geometry']['coordinates']] for premise in premises])
    number_of_clusters = int(points.shape[0] / 8)

    kmeans = KMeans(n_clusters=number_of_clusters, n_init=1, max_iter=1, n_jobs=-1, random_state=0, ).fit(points)

    for idx, dist_point_location in enumerate(kmeans.cluster_centers_):
        dist_points.append({
                'type': "Feature",
                'geometry': {
                    "type": "Point",
                    "coordinates": [dist_point_location[0], dist_point_location[1]]
                },
                'properties': {
                    "id": "distribution_{" + exchange_name + "}{" + str(idx) + "}"
                }
            })        

    return dist_points

def add_technology_to_postcode_areas(postcode_areas, technologies_lut):

    # Process lookup into dictionary
    pcd_to_technology = {}
    for technology in technologies_lut:
        pcd_to_technology[technology['postcode']] = technology
        del pcd_to_technology[technology['postcode']]['postcode']

    # Add properties
    for postcode_area in postcode_areas:
        if postcode_area['properties']['POSTCODE'] in pcd_to_technology:
            postcode_area['properties'].update({
                'max_up_spd': pcd_to_technology[postcode_area['properties']['POSTCODE']]['max_upload_speed'],
                'max_dl_spd': pcd_to_technology[postcode_area['properties']['POSTCODE']]['max_download_speed'],
                'ufbb_avail': pcd_to_technology[postcode_area['properties']['POSTCODE']]['ufbb_availability'],
                'fttp_avail': pcd_to_technology[postcode_area['properties']['POSTCODE']]['fttp_availability'],
                'sfbb_avail': pcd_to_technology[postcode_area['properties']['POSTCODE']]['sfbb_availability'],
                'av_dl_ufbb': pcd_to_technology[postcode_area['properties']['POSTCODE']]['average_data_download_ufbb'],
                'av_dl_adsl': pcd_to_technology[postcode_area['properties']['POSTCODE']]['average_data_download_adsl'],
                'av_dl_sfbb': pcd_to_technology[postcode_area['properties']['POSTCODE']]['average_data_download_sfbb']
            })
        else:
            postcode_area['properties'].update({
                'max_up_spd': 0, 
                'max_dl_spd': 0,
                'ufbb_avail': 0,
                'fttp_avail': 0,
                'sfbb_avail': 0,
                'av_dl_ufbb': 0,
                'av_dl_adsl': 0,
                'av_dl_sfbb': 0
            })
    
    return postcode_areas

def add_technology_to_premises(premises, postcode_areas):

    premises_by_postcode = defaultdict(list)
    for premise in premises:
        premises_by_postcode[premise['properties']['postcode']].append(premise)

    # Join the two
    joined_premises = []
    for postcode_area in postcode_areas:

        # Calculate number of fiber/coax/copper connections in postcode area
        number_of_premises = len(premises_by_postcode[postcode_area['properties']['POSTCODE']]) + 1
        fttp_avail = int(postcode_area['properties']['fttp_avail'])
        ufbb_avail = int(postcode_area['properties']['ufbb_avail'])
        sfbb_avail = int(postcode_area['properties']['sfbb_avail'])
        adsl_avail = 100 - fttp_avail - ufbb_avail - sfbb_avail

        number_of_fttp= round((fttp_avail / 100) * number_of_premises)
        number_of_ufbb = round((ufbb_avail / 100) * number_of_premises)
        number_of_fttc = round((sfbb_avail / 100) * (number_of_premises * 0.8)) # Todo calculate on national scale
        number_of_docsis3 = round((sfbb_avail / 100) * (number_of_premises * 0.2))
        number_of_adsl = round((adsl_avail / 100) * number_of_premises)

        technologies =  ['FTTP'] * number_of_fttp 
        technologies += ['GFast'] * number_of_ufbb 
        technologies += ['FTTC'] * number_of_fttc
        technologies += ['DOCSIS3'] * number_of_docsis3
        technologies += ['ADSL'] * number_of_adsl
        random.shuffle(technologies)

        # Allocate broadband technology and final drop to premises
        for premise, technology in zip(premises_by_postcode[postcode_area['properties']['POSTCODE']], technologies):
            premise['properties']['FTTP'] = 1 if technology == 'FTTP' else 0
            premise['properties']['GFast'] = 1 if technology == 'GFast' else 0
            premise['properties']['FTTC'] = 1 if technology == 'FTTC' else 0
            premise['properties']['DOCSIS3'] = 1 if technology == 'DOCSIS3' else 0
            premise['properties']['ADSL'] = 1 if technology == 'ADSL' else 0

            joined_premises.append(premise)

    return joined_premises

def add_technology_to_premises_link(premises, premise_links):

    premises_technology_by_id = {}
    for premise in premises:
        premises_technology_by_id[premise['properties']['id']] = premise['properties']['technology']

    for premise_link in premise_links:
    
        technology = premises_technology_by_id[premise_link['properties']['origin']]

        if technology in ['FTTP']:
            premise_link['properties']['technology'] = 'fiber'
        elif technology in ['GFast', 'FTTC', 'ADSL']:
            premise_link['properties']['technology'] = 'copper'
        elif technology in ['DOCSIS3']:
            premise_link['properties']['technology'] = 'coax'
    
    return premise_links

def add_technology_to_distributions(distributions, premises):

    premises_technology_by_distribution_id = defaultdict(set)
    for premise in premises:
        premises_technology_by_distribution_id[premise['properties']['connection']].add(premise['properties']['technology'])

    for distribution in distributions:
        technologies_serving = premises_technology_by_distribution_id[distribution['properties']['id']]

        distribution['properties']['FTTP'] = 1 if 'FTTP' in technologies_serving else 0
        distribution['properties']['GFast'] = 1 if 'GFast' in technologies_serving else 0
        distribution['properties']['FTTC'] = 1 if 'FTTC' in technologies_serving else 0
        distribution['properties']['DOCSIS3'] = 1 if 'DOCSIS3' in technologies_serving else 0
        distribution['properties']['ADSL'] = 1 if 'ADSL' in technologies_serving else 0

    return distributions

def add_technology_to_link(assets, asset_links):

    assets_technology_by_id = defaultdict(set)
    for asset in assets:
        if asset['properties']['FTTP'] == 1:
            assets_technology_by_id[asset['properties']['id']].add('FTTP')
        if asset['properties']['GFast'] == 1:
            assets_technology_by_id[asset['properties']['id']].add('GFast')
        if asset['properties']['FTTC'] == 1:
            assets_technology_by_id[asset['properties']['id']].add('FTTC')
        if asset['properties']['DOCSIS3'] == 1:
            assets_technology_by_id[asset['properties']['id']].add('DOCSIS3')
        if asset['properties']['ADSL'] == 1:
            assets_technology_by_id[asset['properties']['id']].add('ADSL')

    for asset_link in asset_links:
    
        technology = assets_technology_by_id[asset_link['properties']['origin']]

        if 'FTTP' in technology:
            asset_link['properties']['technology'] = 'fiber'
        elif 'GFast' or 'FTTC' or 'ADSL' in technology:
            asset_link['properties']['technology'] = 'copper'
        elif 'DOCSIS3' in technology:
            asset_link['properties']['technology'] = 'coax'
    
    return asset_links

def add_technology_to_assets(assets, clients):

    clients_technology_by_asset_id = defaultdict(set)
    for client in clients:
        if client['properties']['FTTP'] == 1:
            clients_technology_by_asset_id[client['properties']['connection']].add('FTTP')
        if client['properties']['GFast'] == 1:
            clients_technology_by_asset_id[client['properties']['connection']].add('GFast')
        if client['properties']['FTTC'] == 1:
            clients_technology_by_asset_id[client['properties']['connection']].add('FTTC')
        if client['properties']['DOCSIS3'] == 1:
            clients_technology_by_asset_id[client['properties']['connection']].add('DOCSIS3')
        if client['properties']['ADSL'] == 1:
            clients_technology_by_asset_id[client['properties']['connection']].add('ADSL')

    for asset in assets:
        technologies_serving = clients_technology_by_asset_id[asset['properties']['id']]

        asset['properties']['FTTP'] = 1 if 'FTTP' in technologies_serving else 0
        asset['properties']['GFast'] = 1 if 'GFast' in technologies_serving else 0
        asset['properties']['FTTC'] = 1 if 'FTTC' in technologies_serving else 0
        asset['properties']['DOCSIS3'] = 1 if 'DOCSIS3' in technologies_serving else 0
        asset['properties']['ADSL'] = 1 if 'ADSL' in technologies_serving else 0

    return assets

def connect_points_to_area(points, areas):

    idx_areas = index.Index()
    for idx, area in enumerate(areas):
        idx_areas.insert(idx, shape(area['geometry']).bounds, area)

    lut_points = {}
    for dest_point in points:
        lut_points[dest_point['properties']['id']] = dest_point['geometry']['coordinates']

    linked_points = []
    for point in points:
        match = list(idx_areas.intersection(shape(point['geometry']).bounds, objects=True))

        if len(match) > 0:
            point['properties']['connection'] = match[0].object['properties']['id']
            linked_points.append(point)
        else:
            print(point['properties'])
            point['properties']['connection'] = linked_points[-1]['properties']['connection']
            linked_points.append(point)

    return linked_points

#####################################
# PROCESS BOUNDARIES
#####################################

def voronoi_finite_polygons_2d(vor, radius=None):
    
    """
    Reconstruct infinite voronoi regions in a 2D diagram to finite regions.

    Parameters
    ----------
    * vor : Voronoi
        Input diagram
    * radius : float, optional
        Distance to 'points at infinity'.
    Returns
    -------
    regions : list of tuples
        Indices of vertices in each revised Voronoi regions.
    vertices : list of tuples
        Coordinates for revised Voronoi vertices. Same as coordinates
        of input vertices, with 'points at infinity' appended to the
        end.
    """

    if vor.points.shape[1] != 2:
        raise ValueError("Requires 2D input")

    new_regions = []
    new_vertices = vor.vertices.tolist()

    center = vor.points.mean(axis=0)
    if radius is None:
        radius = vor.points.ptp().max()

    # Construct a map containing all ridges for a given point
    all_ridges = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    # Reconstruct infinite regions
    for p1, region in enumerate(vor.point_region):
        vertices = vor.regions[region]

        if all(v >= 0 for v in vertices):
            # finite region
            new_regions.append(vertices)
            continue

        # reconstruct a non-finite region
        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]

        for p2, v1, v2 in ridges:
            if v2 < 0:
                v1, v2 = v2, v1
            if v1 >= 0:
                # finite ridge: already in the region
                continue

            # Compute the missing endpoint of an infinite ridge

            t = vor.points[p2] - vor.points[p1] # tangent
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])  # normal

            midpoint = vor.points[[p1, p2]].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far_point = vor.vertices[v2] + direction * radius

            new_region.append(len(new_vertices))
            new_vertices.append(far_point.tolist())

        # sort region counterclockwise
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:,1] - c[1], vs[:,0] - c[0])
        new_region = np.array(new_region)[np.argsort(angles)]

        # finish
        new_regions.append(new_region.tolist())

    return new_regions, np.asarray(new_vertices)


def generate_voronoi_areas(asset_points, clip_region):

    # Get Points
    idx_asset_areas = index.Index()
    points = np.empty([len(list(asset_points)), 2])
    for idx, asset_point in enumerate(asset_points):
        
        # Prepare voronoi lookup
        points[idx] = asset_point['geometry']['coordinates']

        # Prepare Rtree lookup
        idx_asset_areas.insert(idx, shape(asset_point['geometry']).bounds, asset_point)

    # Compute Voronoi tesselation
    vor = Voronoi(points)
    regions, vertices = voronoi_finite_polygons_2d(vor)

    # Write voronoi polygons
    asset_areas = []
    for region in regions:

        polygon = vertices[region]
        geom = Polygon(polygon)

        asset_points = list(idx_asset_areas.nearest(geom.bounds, 1, objects=True))
        for point in asset_points:
            if geom.contains(shape(point.object['geometry'])):
                asset_point = point

        asset_areas.append({
            'geometry': mapping(geom),
            'properties': {
                'id': asset_point.object['properties']['id']
            }
        })

    # Get region set
    regions = []
    for region in clip_region:
        regions.append(shape(region['geometry']))

    # Merge regions
    u = cascaded_union(regions)

    for asset_area in asset_areas:
        asset_area['geometry'] = mapping(shape(asset_area['geometry']).intersection(u))

    return asset_areas

def generate_exchange_area(exchanges, merge=True):

    exchanges_by_group = {}

    # Loop through all exchanges
    for f in exchanges:

        # Convert Multipolygons to list of polygons
        if (isinstance(shape(f['geometry']), MultiPolygon)):
            polygons = [p.buffer(0) for p in shape(f['geometry'])]
        else:
            polygons = [shape(f['geometry'])]

        # Extend list of geometries, create key (exchange_id) if non existing
        try:
            exchanges_by_group[f['properties']['EX_ID']].extend(polygons)
        except:
            exchanges_by_group[f['properties']['EX_ID']] = []
            exchanges_by_group[f['properties']['EX_ID']].extend(polygons)

    # Write Multipolygons per exchange
    exchange_areas = []
    for exchange, area in exchanges_by_group.items():

        exchange_multipolygon = MultiPolygon(area)
        exchange_areas.append({
            'type': "Feature",
            'geometry': mapping(exchange_multipolygon),
            'properties': {
                'id': exchange
            }
        })

    if merge:
        # Merge MultiPolygons into single Polygon
        removed_islands = []
        for area in exchange_areas:

            # Avoid intersections
            geom = shape(area['geometry']).buffer(0)
            cascaded_geom = unary_union(geom)

            # Remove islands
            # Add removed islands to a list so that they
            # can be merged in later
            if (isinstance(cascaded_geom, MultiPolygon)):
                for idx, p in enumerate(cascaded_geom):
                    if idx == 0:
                        geom = p
                    elif p.area > geom.area:
                        removed_islands.append(geom)
                        geom = p
                    else:
                        removed_islands.append(p)
            else:
                geom = cascaded_geom

            # Write exterior to file as polygon
            exterior = Polygon(list(geom.exterior.coords))

            # Write to output
            area['geometry'] = mapping(exterior)
        
        # Add islands that were removed because they were not 
        # connected to the main polygon and were not recovered
        # because they were on the edge of the map or inbetween
        # exchanges :-). Merge to largest intersecting exchange area.
        idx_exchange_areas = index.Index()
        for idx, exchange_area in enumerate(exchange_areas):
            idx_exchange_areas.insert(idx, shape(exchange_area['geometry']).bounds, exchange_area)
        for island in removed_islands:
            intersections = [n for n in idx_exchange_areas.intersection((island.bounds), objects=True)]

            if len(intersections) > 0:
                for idx, intersection in enumerate(intersections):
                    if idx == 0:
                        merge_with = intersection
                    elif shape(intersection.object['geometry']).intersection(island).length > shape(merge_with.object['geometry']).intersection(island).length:
                        merge_with = intersection

                merged_geom = merge_with.object
                merged_geom['geometry'] = mapping(shape(merged_geom['geometry']).union(island))
                idx_exchange_areas.delete(merge_with.id, shape(merge_with.object['geometry']).bounds)
                idx_exchange_areas.insert(merge_with.id, shape(merged_geom['geometry']).bounds, merged_geom)

        exchange_areas = [n.object for n in idx_exchange_areas.intersection(idx_exchange_areas.bounds, objects=True)]

    return exchange_areas

#####################################
# PLACE ASSETS ON ROADS
#####################################

def estimate_asset_locations_on_road_network(origin_points, matching_area, cachefile=None):
    '''
    Put a cabinet in the representative center of the set of premises served by it
    '''
    ox.config(log_file=False, log_console=False, use_cache=True)

    projUTM = Proj(init='epsg:27700')
    projWGS84 = Proj(init='epsg:4326')

    new_asset_locations = []

    lookup = {}
    if cachefile != None:
        cachefile = os.path.join(DATA_INTERMEDIATE, cachefile)
        if os.path.isfile(cachefile):
            with fiona.open(cachefile, 'r') as source:
                for f in source:
                    lookup[f['geometry']['coordinates'][0]] = f['geometry']['coordinates']

    for area in matching_area:
     
        try:
            graph_loaded = False

            east, north = transform(projUTM, projWGS84, shape(area['geometry']).bounds[2], shape(area['geometry']).bounds[3])
            west, south = transform(projUTM, projWGS84, shape(area['geometry']).bounds[0], shape(area['geometry']).bounds[1])

            origins = [point for point in origin_points if point['properties']['id'] == area['properties']['id']]

            for origin in origins:

                #if tuple(origin['geometry']['coordinates']) not in lookup:

                if graph_loaded == False:
                    G = ox.graph_from_bbox(north, south, east, west, network_type='all', truncate_by_edge=True)
                    graph_loaded = True

                origin_x = origin['geometry']['coordinates'][0]
                origin_y = origin['geometry']['coordinates'][1]

                # Find shortest path between the two
                point1_x, point1_y = transform(projUTM, projWGS84, origin_x, origin_y)

                point1 = (point1_y, point1_x)
                #print(point1)
                origin_node = ox.get_nearest_node(G, point1)

                origin_coords = transform(projWGS84, projUTM, G.node[origin_node]['x'], G.node[origin_node]['y'])

                #else:
                    #origin_coords = lookup[tuple(origin['geometry']['coordinates'])]

                # Map to line
                new_asset_locations.append({
                    'type': "Feature",
                    'geometry': {
                        "type": "Point",
                        "coordinates": origin_coords
                    },
                    'properties': {
                        "id": origin['properties']['id']
                    }
                })
        except:
            print('- Problem with asset location for:')
            print(area['properties'])

    return new_asset_locations

#####################################
# PROCESS LINKS
#####################################

def generate_link_straight_line(origin_points, dest_points):

    lut_dest_points = {}
    for dest_point in dest_points:
        lut_dest_points[dest_point['properties']['id']] = dest_point['geometry']['coordinates']

    links = []
    for origin_point in origin_points:
        try:
            # Get length
            geom = LineString([origin_point['geometry']['coordinates'], lut_dest_points[origin_point['properties']['connection']]])

            links.append({
                'type': "Feature",
                'geometry': mapping(geom),
                'properties': {
                    "origin": origin_point['properties']['id'],
                    "dest": origin_point['properties']['connection'],
                    "length": geom.length
                }
            })
        except:
            print('- Problem with straight line link for:')
            print(origin_point['properties'])
        
    return links

def generate_link_shortest_path(origin_points, dest_points, matching_area, cachefile=None):

    ox.config(log_file=False, log_console=False, use_cache=True)

    projUTM = Proj(init='epsg:27700')
    projWGS84 = Proj(init='epsg:4326')

    links = []

    lookup = {}
    if cachefile != None:
        cachefile = os.path.join(DATA_INTERMEDIATE, cachefile)
        if os.path.isfile(cachefile):
            with fiona.open(cachefile, 'r') as source:
                for f in source:
                    lookup[f['geometry']['coordinates'][0]] = f['geometry']['coordinates']

    for area in matching_area:
        
        destinations = [point for point in dest_points if point['properties']['id'] == area['properties']['id']]

        if len(destinations) > 0:

            try:
                graph_loaded = False

                east, north = transform(projUTM, projWGS84, shape(area['geometry']).bounds[2], shape(area['geometry']).bounds[3])
                west, south = transform(projUTM, projWGS84, shape(area['geometry']).bounds[0], shape(area['geometry']).bounds[1])

                destination = destinations[0]

                origins = [point for point in origin_points if point['properties']['connection'] == area['properties']['id']]

                for origin in origins:

                    if tuple(origin['geometry']['coordinates']) not in lookup:

                        if graph_loaded == False:
                            G = ox.graph_from_bbox(north, south, east, west, network_type='all', truncate_by_edge=True)
                            graph_loaded = True

                        origin_x = origin['geometry']['coordinates'][0]
                        origin_y = origin['geometry']['coordinates'][1]
                        dest_x = destination['geometry']['coordinates'][0]
                        dest_y = destination['geometry']['coordinates'][1]

                        # Find shortest path between the two
                        point1_x, point1_y = transform(projUTM, projWGS84, origin_x, origin_y)
                        point2_x, point2_y = transform(projUTM, projWGS84, dest_x, dest_y)

                        point1 = (point1_y, point1_x)
                        point2 = (point2_y, point2_x)

                        origin_node = ox.get_nearest_node(G, point1)
                        destination_node = ox.get_nearest_node(G, point2)

                        try:
                            if origin_node != destination_node:           
                                # Find the shortest path over the network between these nodes
                                route = nx.shortest_path(G, origin_node, destination_node)

                                # Retrieve route nodes and lookup geographical location
                                routeline = []
                                routeline.append((origin_x, origin_y))
                                for node in route:
                                    routeline.append((transform(projWGS84, projUTM, G.nodes[node]['x'], G.nodes[node]['y'])))
                                routeline.append((dest_x, dest_y))
                                line = routeline
                            else:
                                line = [(origin_x, origin_y), (dest_x, dest_y)]
                        except nx.exception.NetworkXNoPath:
                            line = [(origin_x, origin_y), (dest_x, dest_y)]
                    else:
                        line = lookup[tuple(origin['geometry']['coordinates'])]

                    # Map to line
                    links.append({
                        'type': "Feature",
                        'geometry': {
                            "type": "LineString",
                            "coordinates": line
                        },
                        'properties': {
                            "origin": origin['properties']['id'],
                            "dest": destination['properties']['id'],
                            "length": LineString(line).length
                        }
                    })
            except:
                print('- Problem with shortest path generation for:')
                print(area['properties']['id'])

    return links

def generate_link_with_nearest(origin_points, dest_points):

    idx_dest_points = index.Index()
    for idx, dest_point in enumerate(dest_points):
        idx_dest_points.insert(idx, shape(dest_point['geometry']).bounds, dest_point)

    links = []
    for origin_point in origin_points:
        nearest = list(idx_dest_points.nearest(shape(origin_point['geometry']).bounds, objects=True))[0]

        links.append({
            'type': "Feature",
            'geometry': {
                "type": "LineString",
                "coordinates": [origin_point['geometry']['coordinates'], nearest.object['geometry']['coordinates']]
            },
            'properties': {
                "origin": origin_point['properties']['id'],
                "dest": nearest.object['properties']['id'],
                "length": LineString([origin_point['geometry']['coordinates'], nearest.object['geometry']['coordinates']]).length
            }
        })
    return links

def copy_id_to_name(data):

    for entry in data:
        entry['properties']['name'] = entry['properties']['id']
    return data


#####################################
# WRITE LUTS/ASSETS/LINKS
#####################################

def write_shapefile(data, exchange_name, filename):

    # Translate props to Fiona sink schema
    prop_schema = []
    for name, value in data[0]['properties'].items():
        fiona_prop_type = next((fiona_type for fiona_type, python_type in fiona.FIELD_TYPES_MAP.items() if python_type == type(value)), None)
        prop_schema.append((name, fiona_prop_type))

    sink_driver = 'ESRI Shapefile'
    sink_crs = {'init': 'epsg:27700'}
    sink_schema = {
        'geometry': data[0]['geometry']['type'],
        'properties': OrderedDict(prop_schema)
    }

    # Create path
    directory = os.path.join(DATA_INTERMEDIATE, exchange_name)
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Write all elements to output file
    with fiona.open(os.path.join(directory, filename), 'w', driver=sink_driver, crs=sink_crs, schema=sink_schema) as sink:
        [sink.write(feature) for feature in data]
            
def csv_writer(data, filename, fieldnames):
    """
    Write data to a CSV file path
    """
    with open(os.path.join(DATA_INTERMEDIATE, filename),'w') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames, lineterminator = '\n')
        writer.writeheader()
        writer.writerows(data)

#####################################
# APPLY METHODS
#####################################

if __name__ == "__main__":

    SYSTEM_INPUT = os.path.join('data', 'raw')

    # Read LUTs
    print('Process ' + sys.argv[1])
    exchange_name = sys.argv[1]
    exchange_abbr = sys.argv[1].replace('exchange_', '')

    print('read exchange area')
    exchange_area = read_exchange_area(exchange_name)

    print('read lads')
    geojson_lad_areas = read_lads(exchange_area)

    print('get lad ids')
    lad_ids = get_lad_area_ids(geojson_lad_areas)

    #####
    # Integrate WTP and WTA household data into premises
    # print('Loading MSOA data')
    # MSOA_data = read_msoa_data(lad_ids)

    # print('Loading age data')
    # age_data = read_age_data()

    # print('Loading gender data')
    # gender_data = read_gender_data()

    # print('Loading nation data')
    # nation_data = read_nation_data()
    
    # print('Loading urban_rural data')
    # urban_rural_data = read_urban_rural_data()

    # print('Add country indicator')
    # MSOA_data = add_country_indicator(MSOA_data)

    # print('Adding adoption data to MSOA data')
    # MSOA_data = add_data_to_MSOA_data(age_data, MSOA_data, 'age')
    # MSOA_data = add_data_to_MSOA_data(gender_data, MSOA_data, 'gender')

    # print('Loading OA data')
    # oa_data = read_oa_data()

    # print('Match and convert social grades from NS-Sec to NRS')
    # oa_data = convert_ses_grades(oa_data)
      
    # print('Loading ses data')
    # ses_data = read_ses_data()

    # print('Adding ses adoption data to OA data')
    # oa_data = add_data_to_MSOA_data(ses_data, oa_data, 'ses')

    # print('Adding MSOA data to OA data')
    # final_data = merge_two_lists_of_dicts(MSOA_data, oa_data, 'HID', 'lad', 'year')

    # print('Catching any missing data')    
    # final_data, missing_data = get_missing_ses_key(final_data)

    # print('Calculate product of adoption factors')
    # final_data = calculate_adoption_propensity(final_data)

    # print('Calculate willingness to pay')
    # final_data = calculate_wtp(final_data)

    # print('Aggregating WTP by household')
    # household_wtp = aggregate_wtp_and_wta_by_household(final_data)

    # print('Reading premises data')
    # premises = read_premises_data(exchange_area)

    # print('Expand premises entries')
    # premises = expand_premises(premises)

    # print('Adding household data to premises')
    # premises = merge_prems_and_housholds(premises, household_wtp)

    # print('Write premises_multiple by household to .csv')
    # premises_fieldnames = ['uid','oa','gor','residential_address_count','non_residential_address_count','function','postgis_geom','N','E', 'HID','lad','year','wta','wtp']
    # csv_writer(premises, '{}_premises_data.csv'.format(exchange_abbr), premises_fieldnames)  

    # print('Writing wtp')
    # wta_data_fieldnames = ['HID','lad','year','wta','wtp']
    # csv_writer(household_wtp, '{}_wta_data.csv'.format(exchange_abbr), wta_data_fieldnames)  

    # print('Writing any missing data')
    # missing_data_fieldnames = ['PID','MSOA','lad','gender','age','ethnicity','HID','year', 'nation']
    # csv_writer(missing_data, '{}_missing_data.csv'.format(exchange_abbr), missing_data_fieldnames)  
    ####

    print('read_pcd_to_exchange_lut')
    lut_pcd_to_exchange = read_pcd_to_exchange_lut()

    print('read pcd_to_cabinet_lut')
    lut_pcd_to_cabinet = read_pcd_to_cabinet_lut()

    print('read postcode_areas')
    geojson_postcode_areas = read_postcode_areas(exchange_area)

    print('read pcd_technology_lut')
    lut_pcd_technology = read_postcode_technology_lut()

    print('read city exchange geotypes lut')
    city_exchange_lad_lut = read_city_exchange_geotype_lut()

    # Read Premises/Assets
    print('read premises')
    geojson_layer5_premises = read_premises(exchange_area, exchange_abbr)

    print('read exchanges')
    geojson_layer2_exchanges = read_exchanges(exchange_area)

    # Process/Estimate network hierarchy
    print('add exchange id to postcode areas')
    geojson_postcode_areas = add_exchange_id_to_postcode_areas(geojson_layer2_exchanges, geojson_postcode_areas, lut_pcd_to_exchange)

    print('add cabinet id to postcode areas')
    geojson_postcode_areas = add_cabinet_id_to_postcode_areas(geojson_postcode_areas, lut_pcd_to_cabinet)

    print('add postcode to premises')
    geojson_layer5_premises = add_postcode_to_premises(geojson_layer5_premises, geojson_postcode_areas)

    print('add LAD to premises')
    geojson_layer5_premises = add_lad_to_matching_area(geojson_layer5_premises, geojson_lad_areas)

    print('add LAD to exchanges')
    geojson_layer2_exchanges = add_lad_to_exchanges(geojson_layer2_exchanges, geojson_lad_areas)

    print('merge geotype info by LAD to exchanges')
    geojson_layer2_exchanges = add_urban_geotype_to_exchanges(geojson_layer2_exchanges, city_exchange_lad_lut)

    # Process/Estimate assets    
    print('complement cabinet locations as expected for this geotype')
    geojson_layer3_cabinets = complement_postcode_cabinets(geojson_postcode_areas, geojson_layer5_premises, geojson_layer2_exchanges, exchange_abbr)

    print('allocating cabinet to premises')
    geojson_layer5_premises = allocate_to_cabinet(geojson_layer5_premises, geojson_layer3_cabinets)

    print('allocating cabinet to pcd_areas')
    geojson_postcode_areas = allocate_to_cabinet(geojson_postcode_areas, geojson_layer3_cabinets)

    print('estimate location of distribution points')
    geojson_layer4_distributions = estimate_dist_points(geojson_layer5_premises, exchange_abbr)

    print('estimate cabinet locations')
    geojson_layer3_cabinets = estimate_cabinet_locations(geojson_layer5_premises)

    # Process/Estimate boundaries
    print('generate cabinet areas')
    geojson_cabinet_areas = generate_voronoi_areas(geojson_layer3_cabinets, geojson_postcode_areas)

    print('generate distribution areas')
    geojson_distribution_areas = generate_voronoi_areas(geojson_layer4_distributions, geojson_postcode_areas)

    print('generate exchange areas')
    geojson_exchange_areas = generate_exchange_area(geojson_postcode_areas)

    #Place assets on roads     
    print('estimate cabinet locations on road network')
    geojson_layer3_cabinets = estimate_asset_locations_on_road_network(geojson_layer3_cabinets, geojson_cabinet_areas)
   
    print('estimate dist points on road network')
    geojson_layer4_distributions = estimate_asset_locations_on_road_network(geojson_layer4_distributions, geojson_distribution_areas)

    # Connect assets
    print('connect premises to distributions')
    geojson_layer5_premises = connect_points_to_area(geojson_layer5_premises, geojson_distribution_areas)

    print('connect distributions to cabinets')
    geojson_layer4_distributions = connect_points_to_area(geojson_layer4_distributions, geojson_cabinet_areas)

    print('connect cabinets to exchanges')
    geojson_layer3_cabinets = connect_points_to_area(geojson_layer3_cabinets, geojson_exchange_areas)

    # Process/Estimate links
    print('generate links layer 5')
    geojson_layer5_premises_links = generate_link_straight_line(geojson_layer5_premises, geojson_layer4_distributions)

    print('generate links layer 4')
    geojson_layer4_distributions_links = generate_link_shortest_path(geojson_layer4_distributions, geojson_layer3_cabinets, geojson_cabinet_areas)

    print('generate links layer 3')
    geojson_layer3_cabinets_links = generate_link_shortest_path(geojson_layer3_cabinets, geojson_layer2_exchanges, geojson_exchange_areas)

    # Add technology to network and process this into the network hierachy
    print('add technology to postcode areas')
    geojson_postcode_areas = add_technology_to_postcode_areas(geojson_postcode_areas, lut_pcd_technology)

    print('add technology to premises')
    geojson_layer5_premises = add_technology_to_premises(geojson_layer5_premises, geojson_postcode_areas)

    print('add technology to premises links (finaldrop)')
    geojson_layer5_premises_links = add_technology_to_link(geojson_layer5_premises, geojson_layer5_premises_links)

    print('add technology to distributions')
    geojson_layer4_distributions = add_technology_to_assets(geojson_layer4_distributions, geojson_layer5_premises)

    print('add technology to distribution links')
    geojson_layer4_distributions_links = add_technology_to_link(geojson_layer4_distributions, geojson_layer4_distributions_links)

    print('add technology to cabinets')
    geojson_layer3_cabinets = add_technology_to_assets(geojson_layer3_cabinets, geojson_layer4_distributions)
    
    print('add technology to cabinet links')
    geojson_layer3_cabinets_links = add_technology_to_link(geojson_layer3_cabinets, geojson_layer3_cabinets_links)

    print('add technology to exchanges')
    geojson_layer2_exchanges = add_technology_to_assets(geojson_layer2_exchanges, geojson_layer3_cabinets)

    # Copy id to name (required for smif outputs)
    print('copy id to name (distributions)')
    geojson_layer4_distributions = copy_id_to_name(geojson_layer4_distributions)

    print('copy id to name (cabinets)')
    geojson_layer3_cabinets = copy_id_to_name(geojson_layer3_cabinets)

    # Write lookups (for debug purposes)
    print('write postcode_areas')
    write_shapefile(geojson_postcode_areas,  exchange_name, '_postcode_areas.shp')

    print('write distribution_areas')
    write_shapefile(geojson_distribution_areas,  exchange_name, '_distribution_areas.shp')

    print('write cabinet_areas')
    write_shapefile(geojson_cabinet_areas,  exchange_name, '_cabinet_areas.shp')

    print('write exchange_areas')
    write_shapefile(geojson_exchange_areas,  exchange_name, '_exchange_areas.shp')

    # Write assets
    print('write premises')
    write_shapefile(geojson_layer5_premises,  exchange_name, 'assets_layer5_premises.shp')

    print('write distribution points')
    write_shapefile(geojson_layer4_distributions,  exchange_name, 'assets_layer4_distributions.shp')

    print('write cabinets')
    write_shapefile(geojson_layer3_cabinets,  exchange_name, 'assets_layer3_cabinets.shp')

    print('write exchanges')
    write_shapefile(geojson_layer2_exchanges,  exchange_name, 'assets_layer2_exchanges.shp')

    # Write links
    print('write links layer5')
    write_shapefile(geojson_layer5_premises_links,  exchange_name, 'links_layer5_premises.shp')

    print('write links layer4')
    write_shapefile(geojson_layer4_distributions_links,  exchange_name, 'links_layer4_distributions.shp')

    print('write links layer3')
    write_shapefile(geojson_layer3_cabinets_links,  exchange_name, 'links_layer3_cabinets.shp')

    end = time.time()
    print("script finished")
    print("script took {} minutes to complete".format(round((end - start)/60, 2))) 


