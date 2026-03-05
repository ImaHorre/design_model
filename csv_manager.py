"""
CSV Manager Agent

Maintains and updates the CSV database with extracted metadata.
Handles incremental updates, data validation, and timestamp tracking.
"""

import os
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CSVManager:
    """
    Manages the CSV database for measurement data.

    Single wide table schema with all metadata and measurements.
    Handles incremental updates and maintains data consistency.
    """

    # CSV Schema columns
    COLUMNS = [
        # Device information
        'device_type', 'device_id', 'wafer', 'shim', 'replica',

        # Temporal data
        'bonding_date', 'testing_date',

        # Experimental conditions
        'aqueous_fluid', 'oil_fluid',
        'aqueous_flowrate', 'aqueous_flowrate_unit',
        'oil_pressure', 'oil_pressure_unit',

        # Measurement details
        'measurement_type', 'dfu_row', 'roi',
        'measurement_area', 'timepoint',
        'file_name', 'file_type',

        # Droplet size measurements (from CSV files)
        'droplet_size_mean', 'droplet_size_std',
        'droplet_size_min', 'droplet_size_max', 'droplet_count',

        # Frequency measurements (from TXT files)
        'frequency_mean', 'frequency_min', 'frequency_max', 'frequency_count',

        # Data quality
        'parse_quality', 'date_validation_warning',

        # Metadata
        'raw_path', 'download_url', 'scan_timestamp', 'extraction_timestamp'
    ]

    def __init__(self, csv_path: str = None):
        """
        Initialize CSV Manager.

        Args:
            csv_path: Path to CSV database file
        """
        self.csv_path = csv_path or os.getenv('CSV_DATABASE_PATH', 'data/database.csv')
        self.timestamp_file = os.getenv('LAST_SCAN_TIMESTAMP_FILE', 'data/last_scan.txt')

        # Create data directory if it doesn't exist
        Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)

        # Load or create database
        self.df = self._load_or_create_database()

    def _flatten_metadata(self, metadata: Dict) -> Dict:
        """
        Flatten nested file_content_data into top-level fields.

        Args:
            metadata: Metadata dict from Extractor (may contain nested file_content_data)

        Returns:
            Flattened dict with all fields at top level
        """
        flattened = metadata.copy()

        # Extract and flatten file_content_data if present
        if 'file_content_data' in flattened:
            content_data = flattened.pop('file_content_data')

            if isinstance(content_data, dict):
                # Extract measurement fields from nested data
                measurement_fields = [
                    'droplet_size_mean', 'droplet_size_std',
                    'droplet_size_min', 'droplet_size_max', 'droplet_count',
                    'frequency_mean', 'frequency_min', 'frequency_max', 'frequency_count'
                ]

                for field in measurement_fields:
                    if field in content_data:
                        flattened[field] = content_data[field]

        # Remove path_parts if present (not needed in CSV)
        if 'path_parts' in flattened:
            flattened.pop('path_parts')

        return flattened

    def _load_or_create_database(self) -> pd.DataFrame:
        """Load existing database or create new one."""
        if os.path.exists(self.csv_path):
            logger.info(f"Loading existing database: {self.csv_path}")
            df = pd.read_csv(self.csv_path)
            logger.info(f"Loaded {len(df)} records")
            return df
        else:
            logger.info(f"Creating new database: {self.csv_path}")
            df = pd.DataFrame(columns=self.COLUMNS)
            return df

    def add_records(self, metadata_list: List[Dict]) -> int:
        """
        Add new records to database (with duplicate checking).

        Args:
            metadata_list: List of metadata dicts from Extractor

        Returns:
            Number of records added
        """
        if not metadata_list:
            logger.warning("No records to add")
            return 0

        # Flatten nested file_content_data and prepare records
        flattened_records = []
        for metadata in metadata_list:
            flattened = self._flatten_metadata(metadata)
            flattened_records.append(flattened)

        # Convert metadata to DataFrame
        new_df = pd.DataFrame(flattened_records)

        # Add scan timestamp
        new_df['scan_timestamp'] = datetime.now().isoformat()

        # Check for duplicates (skip records with same raw_path)
        if 'raw_path' in new_df.columns and len(self.df) > 0:
            existing_paths = set(self.df['raw_path'].dropna())
            new_df = new_df[~new_df['raw_path'].isin(existing_paths)]

            if len(new_df) == 0:
                logger.info("No new records to add (all duplicates)")
                return 0

        # Ensure all required columns exist
        for col in self.COLUMNS:
            if col not in new_df.columns:
                new_df[col] = None

        # Select only defined columns (drop any extras)
        new_df = new_df[self.COLUMNS]

        # Append to existing database
        self.df = pd.concat([self.df, new_df], ignore_index=True)

        logger.info(f"Added {len(new_df)} new records")
        return len(new_df)

    def update_records(self, metadata_list: List[Dict]) -> int:
        """
        Update existing records or add new ones.

        Uses raw_path as unique identifier.

        Args:
            metadata_list: List of metadata dicts

        Returns:
            Number of records updated/added
        """
        if not metadata_list:
            return 0

        updated_count = 0
        added_count = 0

        for metadata in metadata_list:
            raw_path = metadata.get('raw_path')
            if not raw_path:
                continue

            # Flatten nested data
            flattened = self._flatten_metadata(metadata)

            # Check if record exists
            existing_idx = self.df[self.df['raw_path'] == raw_path].index

            if len(existing_idx) > 0:
                # Update existing record
                for key, value in flattened.items():
                    if key in self.COLUMNS:
                        self.df.loc[existing_idx[0], key] = value

                self.df.loc[existing_idx[0], 'scan_timestamp'] = datetime.now().isoformat()
                updated_count += 1
            else:
                # Add new record
                self.add_records([metadata])
                added_count += 1

        logger.info(f"Updated {updated_count} records, added {added_count} new records")
        return updated_count + added_count

    def remove_deleted_files(self, current_file_paths: List[str]) -> int:
        """
        Remove records for files that no longer exist.

        Args:
            current_file_paths: List of currently existing file paths

        Returns:
            Number of records removed
        """
        current_paths_set = set(current_file_paths)
        existing_paths = set(self.df['raw_path'].dropna())

        deleted_paths = existing_paths - current_paths_set

        if deleted_paths:
            logger.info(f"Removing {len(deleted_paths)} deleted files from database")
            self.df = self.df[~self.df['raw_path'].isin(deleted_paths)]
            return len(deleted_paths)

        return 0

    def save(self):
        """Save database to CSV file."""
        # Create backup if file exists
        if os.path.exists(self.csv_path):
            backup_path = f"{self.csv_path}.backup"
            self.df.to_csv(backup_path, index=False)
            logger.info(f"Backup saved: {backup_path}")

        # Save current database
        self.df.to_csv(self.csv_path, index=False)
        logger.info(f"Database saved: {self.csv_path} ({len(self.df)} records)")

    def get_last_scan_timestamp(self) -> Optional[datetime]:
        """Get timestamp of last scan."""
        if os.path.exists(self.timestamp_file):
            with open(self.timestamp_file, 'r') as f:
                timestamp_str = f.read().strip()
                return datetime.fromisoformat(timestamp_str)
        return None

    def update_scan_timestamp(self):
        """Update last scan timestamp to now."""
        Path(self.timestamp_file).parent.mkdir(parents=True, exist_ok=True)

        with open(self.timestamp_file, 'w') as f:
            f.write(datetime.now().isoformat())

        logger.info("Scan timestamp updated")

    def query(self, **filters) -> pd.DataFrame:
        """
        Query database with filters.

        Args:
            **filters: Column=value pairs to filter by

        Returns:
            Filtered DataFrame

        Example:
            manager.query(device_type='W13', aqueous_flowrate=5)
        """
        result = self.df.copy()

        for column, value in filters.items():
            if column in result.columns:
                result = result[result[column] == value]

        logger.info(f"Query returned {len(result)} records")
        return result

    def get_summary(self) -> Dict:
        """Get summary statistics of database."""
        # Handle date range safely for string dates
        date_range = {'earliest': None, 'latest': None}
        if 'testing_date' in self.df and len(self.df) > 0:
            valid_dates = self.df['testing_date'].dropna()
            if len(valid_dates) > 0:
                date_range = {
                    'earliest': str(valid_dates.min()),
                    'latest': str(valid_dates.max())
                }

        summary = {
            'total_records': len(self.df),
            'device_types': self.df['device_type'].nunique() if 'device_type' in self.df else 0,
            'unique_devices': self.df['device_id'].nunique() if 'device_id' in self.df else 0,
            'date_range': date_range,
            'measurement_files': {
                'csv': len(self.df[self.df['file_type'] == 'csv']) if 'file_type' in self.df else 0,
                'txt': len(self.df[self.df['file_type'] == 'txt']) if 'file_type' in self.df else 0
            },
            'parse_quality': self.df['parse_quality'].value_counts().to_dict() if 'parse_quality' in self.df else {}
        }
        return summary

    def print_summary(self):
        """Print human-readable summary of database."""
        summary = self.get_summary()

        print("\n" + "="*60)
        print("DATABASE SUMMARY")
        print("="*60)
        print(f"Total Records: {summary['total_records']}")
        print(f"Device Types: {summary['device_types']}")
        print(f"Unique Devices: {summary['unique_devices']}")
        print(f"\nDate Range:")
        print(f"  Earliest: {summary['date_range']['earliest']}")
        print(f"  Latest: {summary['date_range']['latest']}")
        print(f"\nMeasurement Files:")
        print(f"  CSV files: {summary['measurement_files']['csv']}")
        print(f"  TXT files: {summary['measurement_files']['txt']}")
        print(f"\nParse Quality:")
        for quality, count in summary['parse_quality'].items():
            print(f"  {quality}: {count}")
        print("="*60 + "\n")


# Example usage
if __name__ == "__main__":
    manager = CSVManager()

    # Example: Add some test data
    test_metadata = {
        'device_type': 'W13',
        'device_id': 'W13_S1_R2',
        'wafer': 13,
        'shim': 1,
        'replica': 2,
        'bonding_date': '2025-10-06',
        'testing_date': '2025-10-23',
        'aqueous_fluid': 'NaCas',
        'oil_fluid': 'SO',
        'aqueous_flowrate': 5,
        'oil_pressure': 150,
        'measurement_type': 'dfu_measure',
        'dfu_row': 1,
        'file_name': 'DFU1.csv',
        'raw_path': 'W13_S1_R2/06102025/23102025/NaCas_SO/5mlhr150mbar/dfu_measure/DFU1.csv',
        'parse_quality': 'complete'
    }

    manager.add_records([test_metadata])
    manager.save()
    manager.print_summary()
