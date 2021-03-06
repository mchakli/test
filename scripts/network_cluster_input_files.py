import os
import os.path
from pprint import pprint
import configparser
import csv
import fiona
import numpy as np
import random
import glob

from shapely.geometry import shape, Point, LineString, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union, cascaded_union
from pyproj import Proj, transform
from rtree import index

from collections import OrderedDict, defaultdict

import osmnx as ox, networkx as nx

CONFIG = configparser.ConfigParser()
CONFIG.read(os.path.join(os.path.dirname(__file__), 'script_config.ini'))
BASE_PATH = CONFIG['file_locations']['base_path']

#####################################
# setup file locations and data files
#####################################

DATA_RAW = os.path.join(BASE_PATH, 'raw')
DATA_INTERMEDIATE = os.path.join(BASE_PATH, 'intermediate')

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

    with open(os.path.join(DATA_RAW, 'network_hierarchy_data', 'January 2013 PCP to Postcode File Part One.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(DATA_RAW, 'network_hierarchy_data', 'January 2013 PCP to Postcode File Part One.csv'), 'r',  encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(DATA_RAW, 'network_hierarchy_data', 'pcp.to.pcd.dec.11.one.csv'), 'r',  encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        for skip in range(11):
            next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(DATA_RAW, 'network_hierarchy_data', 'pcp.to.pcd.dec.11.two.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    with open(os.path.join(DATA_RAW, 'network_hierarchy_data', 'from_tomasso_valletti.csv'), 'r', encoding='utf8', errors='replace') as system_file:
        reader = csv.reader(system_file)
        next(reader)
        for line in reader:
            pcd_to_exchange_data.append({
                'exchange_id': line[0],
                'postcode': line[1].replace(" ", "")
            })

    ### find unique values in list of dicts
    return list({pcd['postcode']:pcd for pcd in pcd_to_exchange_data}.values())

def read_postcode_areas():
    
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

    postcode_areas = []

    pathlist = glob.iglob(os.path.join(DATA_RAW, 'codepoint', 'codepoint-poly_2429451') + '/**/*.shp', recursive=True)

    for path in pathlist:

        # Initialze Rtree
        idx = index.Index()

        print(path)
        with fiona.open(path, 'r') as source:

            # Store shapes in Rtree
            for src_shape in source:
                idx.insert(int(src_shape['id']), shape(src_shape['geometry']).bounds, src_shape)

            # Split list in regular and vertical postcodes
            postcodes = {}
            vertical_postcodes = {}

            for x in source:

                x['properties']['POSTCODE'] = x['properties']['POSTCODE'].replace(" ", "")
                if x['properties']['POSTCODE'].startswith('V'):
                    vertical_postcodes[x['id']] = x
                else:
                    postcodes[x['id']] = x

            for key, f in vertical_postcodes.items():

                vpost_geom = shape(f['geometry'])
                best_neighbour = {'id': 0, 'intersection': 0}

                # Find best neighbour
                for n in idx.intersection((vpost_geom.bounds), objects=True):
                    if shape(n.object['geometry']).intersection(vpost_geom).length > best_neighbour['intersection'] and n.object['id'] != f['id']:
                        best_neighbour['id'] = n.object['id']
                        best_neighbour['intersection'] = shape(n.object['geometry']).intersection(vpost_geom).length

                # Merge with best neighbour
                neighbour = postcodes[best_neighbour['id']]
                merged_geom = unary_union([shape(neighbour['geometry']), vpost_geom])

                merged_postcode = {
                    'id': neighbour['id'].replace(" ", ""),
                    'properties': neighbour['properties'],
                    'geometry': mapping(merged_geom)
                }

                try:
                    postcodes[merged_postcode['id']] = merged_postcode
                except:
                    raise Exception

            for key, p in postcodes.items():
                p.pop('id')
                postcode_areas.append(p)

    return postcode_areas

def read_exchanges():

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

    exchanges = []

    with open(os.path.join(DATA_RAW, 'layer_2_exchanges', 'final_exchange_pcds.csv'), 'r') as system_file:
        reader = csv.reader(system_file)
        next(reader)
    
        for line in reader:
            exchanges.append({
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

    return exchanges

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

def generate_exchange_area(exchanges, merge=True):

    exchanges_by_group = defaultdict(list)

    # Loop through all exchanges
    print('generate_exchange_area - Group polygons by exchange ID')
    for f in exchanges:

        # Convert Multipolygons to list of polygons
        if (isinstance(shape(f['geometry']), MultiPolygon)):
            polygons = [p.buffer(0) for p in shape(f['geometry'])]
        else:
            polygons = [shape(f['geometry'])]

        exchanges_by_group[f['properties']['EX_ID']].extend(polygons)


    # Write Multipolygons per exchange
    print('generate_exchange_area - Generate multipolygons')
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
        print('generate_exchange_area - Merge multipolygons into singlepolygons')
        # Merge MultiPolygons into single Polygon
        removed_islands = []
        for area in exchange_areas:

            # Avoid intersections
            geom = shape(area['geometry']).buffer(0)
            cascaded_geom = unary_union(geom)

            # Remove islands
            # Keep polygon with largest area
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
        print('generate_exchange_area - Process removed islands')
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

def read_exchange_area():
    with fiona.open(os.path.join(DATA_INTERMEDIATE, '_exchange_areas.shp'), 'r') as source:
        return [exchange for exchange in source]

def write_shapefile(data, path):

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

    # Write all elements to output file
    with fiona.open(os.path.join(DATA_INTERMEDIATE, path), 'w', driver=sink_driver, crs=sink_crs, schema=sink_schema) as sink:
        for feature in data:
            sink.write(feature)

#####################################
# APPLY METHODS
#####################################

if __name__ == "__main__":

    SYSTEM_INPUT = os.path.join('data', 'digital_comms', 'raw')

    if not os.path.isfile(os.path.join(DATA_INTERMEDIATE, '_exchange_areas.shp')):

        # Read LUTs
        print('read_pcd_to_exchange_lut')
        lut_pcd_to_exchange = read_pcd_to_exchange_lut()

        print('read postcode_areas')
        geojson_postcode_areas = read_postcode_areas()

        # Write
        print('write postcode_areas')
        write_shapefile(geojson_postcode_areas, '_postcode_areas.shp')
        
        print('read exchanges')
        geojson_layer2_exchanges = read_exchanges()

        # Process/Estimate network hierarchy
        print('add exchange id to postcode areas')
        geojson_postcode_areas = add_exchange_id_to_postcode_areas(geojson_layer2_exchanges, geojson_postcode_areas, lut_pcd_to_exchange)

        print('generate exchange areas')
        geojson_exchange_areas = generate_exchange_area(geojson_postcode_areas)

        # Write
        print('write exchange_areas')
        write_shapefile(geojson_exchange_areas, '_exchange_areas.shp')

    exchange_areas = read_exchange_area()
    #[print(exchange['properties']['id']) for exchange in exchange_areas]

    print('exchange_EAARR')
    print('exchange_EABTM')
    print('exchange_EABWL')
    print('exchange_EACAM')
    print('exchange_EACFH')
    print('exchange_EACOM')
    print('exchange_EACRH')
    print('exchange_EACTM')
    print('exchange_EAESW')
    print('exchange_EAFUL')
    print('exchange_EAGIR')
    print('exchange_EAHIS')
    print('exchange_EAHST')
    print('exchange_EALNT')
    print('exchange_EAMAD')
    print('exchange_EAMBN')
    print('exchange_EASCI')
    print('exchange_EASIX')
    print('exchange_EASST')
    print('exchange_EASWV')
    print('exchange_EATEV')
    print('exchange_EATRU')
    print('exchange_EAWLM')
    print('exchange_EAWTB')