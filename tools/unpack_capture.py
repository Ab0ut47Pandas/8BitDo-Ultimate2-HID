"""Expand one exported capture for the existing analysis tools."""
import argparse
import gzip
from pathlib import Path
import shutil

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    if args.source.resolve()==args.destination.resolve(): raise ValueError('Source and destination must differ')
    with gzip.open(args.source,'rb') as source,args.destination.open('xb') as destination:
        shutil.copyfileobj(source,destination)
