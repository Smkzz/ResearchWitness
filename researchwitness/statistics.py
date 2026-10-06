"""Bounded exact checks for reported univariate descriptive summaries."""
from __future__ import annotations

import csv
from fractions import Fraction
import io
from pathlib import Path
import re
from typing import Any

from .arithmetic import bounded_fraction, rational
from .strict import Bundle, Invalid, byte_hash, canonical, fields, integer, loads, relative_path, require, text

SUMMARY_CHECK_VERSION = '0.1'
MAX_OBSERVATIONS = 4096
MAX_REPORTED_STATISTICS = 32
MAX_TABULAR_BYTES = 2 * 1024 * 1024
MAX_COLUMNS = 256
MAX_CELL_CHARACTERS = 8192
STATISTICS = {
    'count', 'sum', 'mean', 'median', 'minimum', 'maximum',
    'sample_variance', 'population_variance',
}
DECIMAL_RE = re.compile(r'-?(?:0|[1-9][0-9]{0,63})(?:\.[0-9]{1,64})?\Z')


def capabilities() -> list[dict[str, Any]]:
    return [{
        'kind': 'tabular_summary_consistency',
        'supports': [
            'count', 'sum', 'mean', 'median', 'minimum', 'maximum',
            'sample_variance', 'population_variance',
        ],
        'limits': (
            'One numeric column with 1..4096 exact observations, supplied as rational values or read from '
            'a local CSV/TSV file up to 2 MiB; at most 32 distinct reported summaries; explicit '
            'nonnegative exact tolerances for rounded values.'
        ),
        'input_schema': 'schemas/summary-check.schema.json',
        'example_input': 'examples/paper-review-ledger/summary-check.json',
        'example_command': (
            'python -m researchwitness check-summary examples/paper-review-ledger/summary-check.json'
        ),
        'example_classification': 'SYNTHETIC_REPLAY_FIXTURE',
        'does_not_prove': (
            'Data provenance, source-to-data alignment, whether the selected column or missing-value rule '
            'matches the paper analysis, inferential validity, or a paper-level error.'
        ),
    }]


def _quote_offset(source: dict[str, Any], source_bytes: bytes) -> int:
    quote = source['quote'].encode('utf-8')
    if 'quote_offset' in source:
        offset = integer(source['quote_offset'], 0, len(source_bytes))
        require(source_bytes[offset:offset + len(quote)] == quote,
                'Summary claim quote does not match supplied offset')
        return offset
    first = source_bytes.find(quote)
    require(first >= 0, 'Summary claim quote not found in supplied source text')
    require(source_bytes.find(quote, first + 1) < 0,
            'Summary claim quote is ambiguous; supply quote_offset')
    return first


def _exact_number(value: str) -> Fraction:
    """Parse an exact integer, rational, or finite decimal from a tabular cell."""
    require(type(value) is str and len(value) <= 130,
            'Numeric table cell must be a bounded exact value')
    if '/' not in value and DECIMAL_RE.fullmatch(value):
        negative = value.startswith('-')
        unsigned = value[1:] if negative else value
        if '.' in unsigned:
            whole, fractional = unsigned.split('.', 1)
            numerator = int(whole + fractional)
            if negative:
                numerator = -numerator
            return bounded_fraction(Fraction(numerator, 10 ** len(fractional)))
    return bounded_fraction(rational(value))


def _file_values(spec: Any, bundle: Any) -> tuple[list[Fraction], dict[str, Any]]:
    fields(spec, {'path', 'format', 'header', 'missing_values', 'missing_policy'},
           {'column_name', 'column_index'})
    name = relative_path(spec['path'])
    format_name = spec['format']
    require(format_name in ('csv', 'tsv'), 'Tabular file format must be csv or tsv')
    require(type(spec['header']) is bool, 'Tabular header must be true or false')
    if spec['header']:
        fields(spec, {'path', 'format', 'header', 'missing_values', 'missing_policy',
                      'column_name'})
        column_name = text(spec['column_name'], 200)
        column_index = None
    else:
        fields(spec, {'path', 'format', 'header', 'missing_values', 'missing_policy',
                      'column_index'})
        column_index = integer(spec['column_index'], 0, MAX_COLUMNS - 1)
        column_name = None

    missing_values = spec['missing_values']
    require(type(missing_values) is list and len(missing_values) <= 32,
            'Missing-value list must contain at most 32 strings')
    require(all(type(value) is str and len(value) <= 200 for value in missing_values),
            'Missing-value markers must be bounded strings')
    require(len(set(missing_values)) == len(missing_values),
            'Duplicate missing-value marker')
    missing_policy = spec['missing_policy']
    require(missing_policy in ('reject', 'drop'),
            'Missing-value policy must be reject or drop')

    raw_file = bundle.read(name, MAX_TABULAR_BYTES)
    try:
        decoded = raw_file.decode('utf-8-sig')
        delimiter = ',' if format_name == 'csv' else '\t'
        reader = csv.reader(io.StringIO(decoded, newline=''), delimiter=delimiter, strict=True)
        first_row = next(reader, None)
        require(first_row is not None, 'Tabular file is empty')
        if spec['header']:
            header = first_row
            require(1 <= len(header) <= MAX_COLUMNS,
                    f'Tabular file must have 1 to {MAX_COLUMNS} columns')
            require(all(len(cell) <= MAX_CELL_CHARACTERS for cell in header),
                    'Tabular header cell exceeds the size limit')
            matches = [index for index, cell in enumerate(header) if cell == column_name]
            require(len(matches) == 1, 'Selected column name must occur exactly once in the header')
            column_index = matches[0]
            expected_columns = len(header)
            first_data_row = 1
        else:
            require(1 <= len(first_row) <= MAX_COLUMNS,
                    f'Tabular file must have 1 to {MAX_COLUMNS} columns')
            expected_columns = len(first_row)
            require(column_index < expected_columns,
                    'Selected column index is outside the first record')
            first_data_row = 0

        values: list[Fraction] = []
        included_records: list[int] = []
        missing_records: list[int] = []
        record_count = 0

        def consume(row: list[str]) -> None:
            nonlocal record_count
            record_count += 1
            require(record_count <= MAX_OBSERVATIONS,
                    f'Tabular file exceeds {MAX_OBSERVATIONS} data records')
            require(len(row) == expected_columns,
                    'Tabular file records have inconsistent column counts')
            require(all(len(cell) <= MAX_CELL_CHARACTERS for cell in row),
                    'Tabular cell exceeds the size limit')
            record_number = record_count
            cell = row[column_index]
            if cell in missing_values:
                missing_records.append(record_number)
                require(missing_policy == 'drop',
                        f'Missing value found in selected column at data record {record_number}')
                return
            values.append(_exact_number(cell))
            included_records.append(record_number)

        if first_data_row == 0:
            consume(first_row)
        for row in reader:
            consume(row)
        require(values, 'Tabular file contains no included numeric observations')
    except UnicodeDecodeError as exc:
        raise Invalid('Tabular file must be UTF-8 text') from exc
    except csv.Error as exc:
        raise Invalid('Malformed CSV/TSV input') from exc
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid('Invalid numeric table value') from exc

    return values, {
        'input_kind': 'delimited_file',
        'file': name,
        'format': format_name,
        'file_sha256': byte_hash(raw_file),
        'header_present': spec['header'],
        'column_index': column_index,
        'column_name': column_name,
        'missing_values': missing_values,
        'missing_policy': missing_policy,
        'data_record_count': record_count,
        'record_numbering': '1-based logical data-record order; header excluded.',
        'included_record_numbers': included_records,
        'missing_record_numbers': missing_records,
        'numeric_encoding': 'Exact integer, rational, or finite decimal; decimal values are converted exactly.',
        'selection_semantics': (
            'Reads every data record in order; selects one column; applies only the declared missing-value policy.'
        ),
    }


def validate_summary_check(
    doc: Any,
    source_bytes: bytes,
    raw_input: bytes,
    data_bundle: Any | None = None,
) -> dict[str, Any]:
    """Recompute exact descriptive statistics and compare explicit reported values."""
    fields(doc, {'summary_check_version', 'source', 'data', 'reported'})
    require(doc['summary_check_version'] == SUMMARY_CHECK_VERSION,
            'Unsupported summary-check version')
    source = doc['source']
    fields(source, {'identifier', 'version', 'text_file', 'capture_status', 'quote'}, {'quote_offset'})
    text(source['identifier'], 2000)
    text(source['version'], 100)
    relative_path(source['text_file'])
    require(source['capture_status'] in ('unverified', 'captured', 'synthetic'),
            'Unknown source capture status')
    text(source['quote'], 8000)
    quote_offset = _quote_offset(source, source_bytes)

    data = doc['data']
    fields(data, {'column', 'data_source', 'transformation'}, {'values', 'file'})
    require(('values' in data) != ('file' in data),
            'Data must supply exactly one of values or file')
    text(data['column'], 200)
    text(data['data_source'], 2000)
    text(data['transformation'], 2000)
    if 'values' in data:
        raw_values = data['values']
        require(type(raw_values) is list and 1 <= len(raw_values) <= MAX_OBSERVATIONS,
                f'Need 1 to {MAX_OBSERVATIONS} exact numeric observations')
        values = [rational(value) for value in raw_values]
        extraction: dict[str, Any] = {'input_kind': 'inline_values'}
        values_hash = byte_hash(canonical(raw_values))
    else:
        require(data_bundle is not None,
                'A local file bundle is required for file-backed summary data')
        values, extraction = _file_values(data['file'], data_bundle)
        values_hash = byte_hash(canonical([str(value) for value in values]))

    reported = doc['reported']
    require(type(reported) is list and 1 <= len(reported) <= MAX_REPORTED_STATISTICS,
            f'Need 1 to {MAX_REPORTED_STATISTICS} reported statistics')
    parsed_claims: list[tuple[str, Fraction | int, Fraction]] = []
    seen_statistics: set[str] = set()
    for item in reported:
        fields(item, {'statistic', 'value', 'tolerance'})
        statistic = item['statistic']
        require(type(statistic) is str and statistic in STATISTICS,
                'Unsupported reported statistic')
        require(statistic not in seen_statistics, 'Duplicate reported statistic')
        seen_statistics.add(statistic)
        tolerance = rational(item['tolerance'])
        require(tolerance >= 0, 'Rounding tolerance must be nonnegative')
        if statistic == 'count':
            value: Fraction | int = integer(item['value'], 0, MAX_OBSERVATIONS)
            require(tolerance == 0, 'Count tolerance must be zero')
        else:
            value = rational(item['value'])
        parsed_claims.append((statistic, value, tolerance))

    count = len(values)
    total = Fraction(0)
    squared_deviations = Fraction(0)
    for value in values:
        total = bounded_fraction(total + value)
    mean = bounded_fraction(total / count)
    ordered = sorted(values)
    if count % 2:
        median = ordered[count // 2]
    else:
        median = bounded_fraction((ordered[count // 2 - 1] + ordered[count // 2]) / 2)
    for value in values:
        difference = bounded_fraction(value - mean)
        square = bounded_fraction(difference * difference)
        squared_deviations = bounded_fraction(squared_deviations + square)
    actual: dict[str, Fraction | int] = {
        'count': count,
        'sum': total,
        'mean': mean,
        'median': median,
        'minimum': ordered[0],
        'maximum': ordered[-1],
        'population_variance': bounded_fraction(squared_deviations / count),
    }
    if count > 1:
        actual['sample_variance'] = bounded_fraction(squared_deviations / (count - 1))

    comparisons: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for statistic, reported_value, tolerance in parsed_claims:
        require(statistic in actual, 'Sample variance requires at least two observations')
        observed = actual[statistic]
        difference = (Fraction(observed) - Fraction(reported_value))
        difference = abs(bounded_fraction(difference))
        matches = difference <= tolerance
        record = {
            'statistic': statistic,
            'reported_exact': str(reported_value),
            'computed_exact': str(observed),
            'absolute_difference_exact': str(difference),
            'tolerance_exact': str(tolerance),
            'within_tolerance': matches,
        }
        comparisons.append(record)
        if not matches:
            mismatches.append(record)

    return {
        'decision': ('TABULAR_SUMMARY_MISMATCH_VERIFIED' if mismatches
                     else 'NO_MISMATCH_WITHIN_DECLARED_TOLERANCES'),
        'checker': 'tabular_summary_consistency',
        'checker_version': SUMMARY_CHECK_VERSION,
        'source': {
            'identifier': source['identifier'],
            'version': source['version'],
            'capture_status': source['capture_status'],
            'quote': source['quote'],
            'quote_offset': quote_offset,
            'source_provenance': 'NOT_AUTHENTICATED',
            'source_text_sha256': byte_hash(source_bytes),
        },
        'data': {
            'column': data['column'],
            'data_source_declared': data['data_source'],
            'transformation_declared': data['transformation'],
            'transformation_execution': 'DECLARATION_ONLY_NOT_EXECUTED',
            'provenance_status': 'NOT_AUTHENTICATED',
            'observation_count': count,
            'values_sha256': values_hash,
            'extraction': extraction,
        },
        'comparisons': comparisons,
        'mismatches': mismatches,
        'input_sha256': byte_hash(raw_input),
        'paper_error_established': False,
        'data_to_paper_alignment': 'NOT_ESTABLISHED',
        'meaning': (
            'This result compares exact statistics over the supplied or file-extracted values with the supplied '
            'reported numbers using the declared tolerances. It does not authenticate the data, validate '
            'inclusion/exclusion rules, or establish that the values correspond to the paper.'
        ),
    }


def validate_summary_file(path: Path | str) -> dict[str, Any]:
    """Validate and check a summary-check JSON file with adjacent source text."""
    path = Path(path).absolute()
    bundle = Bundle(path.parent)
    raw = bundle.read(path.name, 2 * 1024 * 1024)
    doc = loads(raw)
    require(type(doc) is dict, 'Summary-check input must be an object')
    source = doc.get('source')
    require(type(source) is dict and type(source.get('text_file')) is str,
            'Summary-check source text path is missing')
    relative_path(source['text_file'])
    source_bytes = bundle.read(source['text_file'])
    try:
        source_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise Invalid('Summary-check source text must be UTF-8') from exc
    return validate_summary_check(doc, source_bytes, raw, bundle)
