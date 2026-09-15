from __future__ import annotations


__all__ = ['args_parser']

from argparse import ArgumentParser


args_parser = ArgumentParser()


args_parser.add_argument('-s', '--safe', action='store_true')
