#!/bin/python3

import argparse
import collections
import dataclasses
import logging
import pathlib
import re
import pickle
import typing
import multiprocessing
import zlib


docsets = [
    'sdk-api/sdk-api-src/content',
    'windows-driver-docs-ddi/wdk-ddi-src/content',
]


class DocsDBStore(collections.UserDict):
    def __setitem__(self, key: str, value: str):
        if not isinstance(value, str):
            raise TypeError('Only string values allowed')

        data = zlib.compress(value.encode())
        return super().__setitem__(key, data)

    def __getitem__(self):
        raise NotImplementedError

    def save(self, filepath: str) -> dict:
        with open(filepath, 'wb') as handle:
            return pickle.dump(self.data, handle, protocol=pickle.HIGHEST_PROTOCOL)


@dataclasses.dataclass(frozen=True)
class FrozenApiDoc(object):
    name: str
    content: str


class ApiDoc(object):
    SKIP_NAME_CHARSET = ('+', '=', '()', '!' , '::')

    def __init__(self, filepath: str, force: bool = False):
        self._filepath = filepath
        with open(self._filepath, "r", errors = "ignore") as infile:
            data = infile.read()

        _, front_matter, *markdown = data.split('---')
        self.front_matter = front_matter
        self.content = '---'.join(markdown)

        if not force and not self.verify():
            raise ValueError(f'invalid file format in {self._filepath}')

    def verify(self) -> bool:
        name = self.name
        if not name:
            return False

        if any([x in name for x in self.SKIP_NAME_CHARSET]):
            logging.debug(f"invalid function name {name} in {self._filepath}")
            return False
        
        return True

    def dump(self, clean_markdown: bool = True):
        if clean_markdown:
            return self._clean_markdown(self.content)

        return self.content

    @staticmethod
    def _clean_markdown(text: str):
        # remove <a>, <div> tags
        text = re.sub(r'\</?(a|div)[^\>]*\>', '', text)

        # remove multiple enters and unnecessary spacing
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'>[\n\r]+<', '><', text)
        text = re.sub(r'[\n\r]+<', '<', text)
        text = re.sub(r'[\n\r]{2,}', '\n\n', text)
        text = text.replace('\n ', ' ')

        # '## -description' -> '## Description'
        text = re.sub(r'# -(.+)', lambda match: f'# {match.group(1).capitalize()}', text)

        text = re.sub(r'# ([^\s]+) function', r'# \1', text)

        # remove "See also" links section
        text = re.sub(r'## See-also[^#]+', '', text, re.MULTILINE)

        # replace markdown links
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'**\g<1>**', text)
        
        # fixing incorrect <table> margin from top 
        offset = 0
        while True:
            start = text.find('<table', offset)
            if start == -1:
                break

            end = text.find('</table>', start)
            cleaned = text[start:end].replace('\n\n', '\n')
            text = text[:start] + cleaned + text[end:]
            offset = start + len(cleaned)

        # table borders and columns width
        text = text.replace(' width="40%"', '').replace(' width="60%"', '')
        text = text.replace('<table>', '<table border="1" cellspacing="0" cellpadding="3">')

        # replace h3 tag with markdown header
        text = re.sub(r'<h3>([^<]+)</h3>', r'\n\n### \g<1>\n\n', text)

        return text

    @property
    def name(self):
        match = re.search(r'title: (.*)', self.front_matter)
        if match is None:
            logging.debug(f"title is not present in {self._filepath}")
            raise False

        title = match.group(1)
        match = re.search(r'([^\s]+) function', title)
        if not match:
            logging.debug(f"unsupported title format in {self._filepath}")
            return False
        return match.group(1).replace('\\', '')

    def __str__(self) -> str:
        return self.dump()


def parse_file(filepath: str) -> typing.Optional[FrozenApiDoc]:
    import traceback
    try:
        doc = ApiDoc(filepath)
        return FrozenApiDoc(doc.name, str(doc))
    except Exception as e:
        # print(traceback.format_exc())
        logging.debug(f"failed to process {filepath}: {e}")
    return None


def parse_from_directory_iter(dirpath: str) -> typing.Generator[FrozenApiDoc, None, None]:
    _dirpath = pathlib.Path(dirpath)

    if not _dirpath.exists() or not _dirpath.is_dir():
        logging.warning(f"{_dirpath} directory could not be found")
        logging.warning("try: git submodule update --recursive")
        logging.warning(f"skipping {_dirpath}")
        return False

    with multiprocessing.Pool() as pool:
        files = filter(lambda x: not x.startswith('_'), map(str, _dirpath.rglob('*.md')))
        for result in pool.map(parse_file, files):
            if result is not None:
                yield result


def main():
    parser = argparse.ArgumentParser(description="msdocviewer parser component") 
    parser.add_argument(
        "dirpath", nargs="?",
        help="dirpath with sdk directories",
        default='.'
    )
    parser.add_argument(
        '-l', '--log', 
        help="Log all parsing errors to debug-parser.log",
        default=None, 
    )
    parser.add_argument(
        '-d', '--debug',
        help="Print lots of debugging statements",
        action="store_const", dest="loglevel", const=logging.DEBUG,
        default=logging.INFO,
    )
    parser.add_argument(
        '-o', '--output', 
        help="output database filepath",
        action="store_const", 
        default='msdocsviewer_ex.db', 
    )

    args = parser.parse_args()
    logging.basicConfig(
        filename=args.log,
        level=args.loglevel,
        format='%(levelname)s - %(message)s',
    )

    logging.info("starting the parsing")
    db = DocsDBStore()
    for docset_path in docsets:
        path = str(pathlib.Path(args.dirpath) / docset_path)
        logging.info(f"parsing {path}")
        for result in parse_from_directory_iter(path):
            db[result.name] = result.content
        logging.info(f"parsing {path} completed")
    logging.info("parsing was finished")

    if len(db) == 0:
        logging.error('no files was parsed, exit')
        exit(0)

    db.save(args.output)
    logging.info(f"saved to {args.output}")
    

if __name__ == "__main__":
    main()
