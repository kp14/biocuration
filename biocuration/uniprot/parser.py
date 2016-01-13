# coding: utf-8
#import functools
import itertools
import logging
import re
from collections import defaultdict


logging.basicConfig(level=logging.WARN)

LINE_ENDINGS = ' \n\r'


class Record():
    '''Class emulating biopython.SwissProt.Record.

    All fields biopython.SwissProt.Record provides are provided, too.
    Addinitional ones also, for convenience.
    '''
    def __init__(self, bag):
        self._bag = bag

    @property
    def entry_name(self):
        return self._bag['ID'][0][0]

    @property
    def data_class(self):
        return self._bag['ID'][0][1].strip(';')

    @property
    def molecule_type(self):
        return None

    @property
    def sequence_length(self):
        return int(self._bag['ID'][0][2])

    @property
    def accessions(self):
        return list(itertools.chain(*self._bag['AC']))

    @property
    def created(self):
        date, _ = self._bag['DT'][0].strip('.').split(', ')
        return (date, 0) # Version is always zero here

    @property
    def sequence_update(self):
        date, version_string = self._bag['DT'][1].strip('.').split(', ')
        version_split = version_string.split()
        return (date, int(version_split[2]))

    @property
    def annotation_update(self):
        date, version_string = self._bag['DT'][2].strip('.').split(', ')
        version_split = version_string.split()
        return (date, int(version_split[2]))

    @property
    def primary_accession(self):
        return self._bag['AC'][0][0]

    @property
    def description(self):
        return ' '.join(self._bag['DE'])

    @property
    def gene_name(self):
        return ' '.join(self._bag['GN'])

    @property
    def organism(self):
        return ' '.join(self._bag['OS'])

    @property
    def organelle(self):
        try:
            return self._bag['OG'][0]
        except IndexError:
            return ''

    @property
    def organism_classification(self):
        return _flatten_lists(self._bag['OC'])

    @property
    def taxonomy_id(self):
        return self._bag['OX']

    @property
    def host_organism(self):
        orgs = []
        for oh_line in self._bag['OH']:
            _, org = oh_line.strip('.').split('; ')
            orgs.append(org)
        return orgs

    @property
    def host_taxonomy_id(self):
        ids = []
        for oh_line in self._bag['OH']:
            id_string, _ = oh_line.strip('.').split('; ')
            _, taxid = id_string.split('=')
            ids.append(taxid)
        return ids

    @property
    def references(self):
        ref_list = []
        for num, data in self._bag['RF'].items():
            ref_list.append(Reference(num, data))
        return ref_list

    @property
    #@functools.lru_cache(maxsize=1)
    def comments(self):
        concat = ' '.join(self._bag['CC'])
        topics = concat.split('-!- ')
        topics = [x.strip() for x in topics]
        return topics[1:]

    @property
    def cross_references(self):
        return self._bag['DR']

    @property
    def keywords(self):
        return _flatten_lists(self._bag['KW'])

    @property
    #@functools.lru_cache(maxsize=1)
    def seqinfo(self):
        tokens = self._bag['SQ'][0].split()
        length = int(tokens[1])
        mol_weight = int(tokens[3])
        crc64 = tokens[5]
        return (length, mol_weight, crc64)

    @property
    #@functools.lru_cache(maxsize=1)
    def features(self):
        try:
            return self._features
        except AttributeError:
            feature_list = []
            for item in self._bag['FT']:
                logging.debug('Looking at feature: {}'.format(item))
                item_length = len(item)
                if item_length == 4:
                    feature_list.append(item)
                elif item_length == 1:
                    if item[0].startswith('/FTId='):
                        stripped = item[0].strip('.;')
                        try:
                            feature_list[-1].append(stripped[6:])
                        except IndexError:
                            print(feature_list, item, stripped)
                            raise Exception
                    else:
                        last_item = feature_list[-1].pop()
                        extended_item = ' '.join([last_item, item[0]])
                        try:
                            feature_list[-1].append(extended_item)
                        except IndexError:
                            print(feature_list, item, extended_item, last_item)
                            raise Exception
                elif item_length == 3:
                    item.append('')
                    feature_list.append(item)
                else:
                    logging.error('Feature of wrong length: {}'.format(item))
                    raise ValueError('ERROR in feature: {}'.format(item_length))
            for item in feature_list:
                if len(item) == 4:
                    item.append('')
            tuple_list = [tuple(item) for item in feature_list]
            self._features = tuple_list
            return self._features

    @property
    def sequence(self):
        gapped_seq = ''.join(self._bag['  '])
        seq = gapped_seq.replace(' ', '')
        return seq


class Reference():

    def __init__(self, num, data):
        self._num = num
        self._data = data

    @property
    def number(self):
        return self._num

    @property
    def positions(self):
        return self._data['RP']

    @property
    def comments(self):
        return self._parse_rc_rx('RC')

    @property
    def references(self):
        return self._parse_rc_rx('RX')

    @property
    def authors(self):
        if len(self._data['RA']) == 1:
            authors = self._data['RA'][0]
        else:
            authors = ' '.join(self._data['RA'])
        return authors.rstrip(';')

    @property
    def title(self):
        title = ' '.join(self._data['RT'])
        return title.strip('";')

    @property
    def location(self):
        return self._data['RL'][0]

    def _parse_rc_rx(self, context):
        context = context
        if len(self._data[context]) == 1:
            comments = self._data[context][0]
        else:
            comments = ' '.join(self._data[context])
        tokens = comments.split('; ')
        c_tuples = []
        for tok in tokens:
            if tok:
                key, val = tok.rstrip(';').split('=')
                c_tuples.append((key, val))
        return c_tuples

def _flatten_lists(lol):
    '''Flatten list of lists.'''
    flat = []
    for sublist in lol:
        flat.extend(sublist)
    return flat


def parse_txt(handle):
    bag, context = _set_up()
    for line in handle:
        line_type, line = line[:2], line[5:]
        stripped_line = line.rstrip(LINE_ENDINGS)
#        stripped_line = line
        try:
            if line_type.startswith('R'):
                if line_type == 'RN':
                    number = _extract_ref_number(line)
                    context = number
                    bag['RF'][context] = defaultdict(list)
                else:
                    bag['RF'][context][line_type].append(stripped_line)
            value = PARSER_MAP[line_type](stripped_line)
            if value:
                bag[line_type].append(value)
        except KeyError:
            if line_type == '//':
                yield bag
                bag, context = _set_up()
            else:
                logging.debug("Unknown line type: {}".format(line_type))


def parse_txt_compatible(handle):
    for bag in parse_txt(handle):
        yield Record(bag)

def _set_up():
    bag = defaultdict(list)
    bag['RF'] = {}
    context = None
    return bag, context

def _extract_ref_number(line):
    pattern = re.compile('(\[[0-9]+\])')
    tokens = re.split(pattern, line)
    number = int(tokens[1].strip('[]'))
    return number

def _parse_generic(line):
    return line


def _parse_id(line):
    id_line_tokens = line.split()
    return id_line_tokens


def _parse_accessions(line):
    stripped_line = line.strip(';.')
    tokens = stripped_line.split(';')
    accs = [x.strip() for x in tokens]
    return accs


def _parse_species(line):
    """Extract species information from OS line

    :line: TODO
    :returns: TODO

    """
    species = line.split(' (')[0]
    return species


def _parse_taxonomy(line):
    stripped_line = line.strip(';.')
    tokens = stripped_line.split(';')
    nodes = [x.strip() for x in tokens]
    return nodes


def _parse_taxid(line):
    """Extract NCBI taxonomy ID.

    :line: TODO
    :returns: TODO

    """
    _, id_string = line.strip(';').split('=')
    taxid = id_string.split()[0]
    return taxid


def _parse_cc(line):
    if not line[0:3] in ['---', 'Cop', 'Dis']:
        return line

def _parse_dr(line):
    stripped_line = line.strip(';.')
    tokens = stripped_line.split('; ')
    return tuple(tokens)


def _parse_kw(line):
    stripped_line = line.strip(';.')
    tokens = stripped_line.split(';')
    kwds = [x.strip() for x in tokens]
    return kwds


def _parse_ft(line):
    '''Parses components of a UniProt flatfile FT line.

    FT lines follow the following format:
    [FT   ]KEY      x      y       Description.
    Assuming a maximum value for x or y of 99999, which seems OK as
    the longest sequences are about 35000 amino acids. X and y can
    be numbers or of format >123 etc.

    Returns:
    list
    '''

    feature = []

    key = line[0:8].strip()
    start = line[10:15].strip()
    end = line[17:22].strip()
    description = line[30:].strip()

    if not key == '':
        feature.append(key)
    if not start == '':
        try:
            start = int(start)
        except ValueError:
            pass
        feature.append(start)
    if not end == '':
        try:
            end = int(end)
        except ValueError:
            pass
        feature.append(end)
    if not description == '':
        feature.append(description)
    assert len(feature) in [1, 3, 4]
    logging.debug('Parsed FT: {}'.format(feature))
    return feature


PARSER_MAP = {"ID": _parse_id,
              "AC": _parse_accessions,
              "DT": _parse_generic,
              "DE": _parse_generic,
              "GN": _parse_generic,
              "OS": _parse_generic,
              "OG": _parse_generic,
              "OC": _parse_taxonomy,
              "OH": _parse_generic,
              "OX": _parse_taxid,
              "RF": _parse_generic,
              "CC": _parse_cc,
              "DR": _parse_dr,
              "KW": _parse_kw,
              "PE": _parse_generic,
              "FT": _parse_ft,
              "**": _parse_generic,
              "SQ": _parse_generic,
              "  ": _parse_generic}

if __name__ == '__main__':

    import datetime

    from Bio import SwissProt

    datafile = 'uniprot_sprot.dat'
    start = datetime.datetime.now()

    with open(datafile, 'r', encoding='ascii') as data:
#        for entry in SwissProt.parse(data):
#            print(entry.keywords)
#        data.seek(0)
        for entry in parse_txt_compatible(data):
            for feat in entry.features:
                if feat[0] == 'REGION' and 'Necessary for binding' in feat[3]:
                    print(feat)
    end = datetime.datetime.now()
    print(end-start)