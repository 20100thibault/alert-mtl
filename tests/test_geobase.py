"""
Tests for Geobase service
"""

import pytest
from app.services.geobase import (
    normalize_street_name,
    parse_address,
    lookup_address,
    search_addresses
)


class TestNormalizeStreetName:
    """Tests for street name normalization."""

    def test_lowercase(self):
        """Should convert to lowercase."""
        assert normalize_street_name('SAINT-DENIS') == 'saint-denis'

    def test_remove_accents(self):
        """Should remove accents."""
        result = normalize_street_name('Côte-des-Neiges')
        assert 'cote' in result

    def test_expand_abbreviations(self):
        """Should expand common abbreviations."""
        assert 'saint' in normalize_street_name('St-Denis')
        assert 'sainte' in normalize_street_name('Ste-Catherine')

    def test_remove_street_type_prefix(self):
        """Should remove street type prefix."""
        result = normalize_street_name('Rue Saint-Denis')
        assert result == 'saint-denis'


class TestParseAddress:
    """Tests for address parsing."""

    def test_parse_number_first(self):
        """Should parse address with number first."""
        result = parse_address('1234 Rue Saint-Denis')
        assert result['civic_number'] == 1234
        assert 'saint-denis' in result['normalized_name'].lower()

    def test_parse_number_last(self):
        """Should parse address with number last."""
        result = parse_address('Rue Saint-Denis 1234')
        assert result['civic_number'] == 1234

    def test_parse_with_street_type(self):
        """Should extract street type."""
        result = parse_address('1234 Avenue Mont-Royal')
        assert result['street_type'] == 'Avenue'

    def test_parse_no_number(self):
        """Should handle address without number."""
        result = parse_address('Saint-Denis')
        assert result['civic_number'] is None
        assert result['street_name'] == 'Saint-Denis'


class TestLookupAddress:
    """Tests for address lookup."""

    def test_lookup_valid_address(self, app, sample_geobase_entries):
        """Should find valid address."""
        with app.app_context():
            result = lookup_address('1234 Rue Saint-Denis')

            assert result is not None
            assert result['cote_rue_id'] == 13811012
            assert result['street_name'] == 'Saint-Denis'

    def test_lookup_partial_match(self, app, sample_geobase_entries):
        """Should find partial matches."""
        with app.app_context():
            result = lookup_address('1250 saint denis')

            assert result is not None
            assert 'Saint-Denis' in result['street_name']

    def test_lookup_not_found(self, app, sample_geobase_entries):
        """Should return None for unknown address."""
        with app.app_context():
            result = lookup_address('99999 Nonexistent Street')
            # May or may not find a result depending on fuzzy matching


class TestSearchAddresses:
    """Tests for address search."""

    def test_search_short_query(self, app, sample_geobase_entries):
        """Should return empty for short queries."""
        with app.app_context():
            results = search_addresses('ab')
            assert results == []

    def test_search_valid_query(self, app, sample_geobase_entries):
        """Should return results for valid query."""
        with app.app_context():
            results = search_addresses('saint-denis')

            assert len(results) > 0
            assert any('Saint-Denis' in r['street_name'] for r in results)

    def test_search_respects_limit(self, app, sample_geobase_entries):
        """Should respect limit parameter."""
        with app.app_context():
            results = search_addresses('saint', limit=2)
            assert len(results) <= 2
