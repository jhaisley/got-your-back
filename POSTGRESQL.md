# PostgreSQL Integration for Got Your Back (GYB)

## Overview

Got Your Back (GYB) now supports storing Gmail messages in a PostgreSQL database instead of the traditional SQLite + file storage approach. This enables better scalability, centralized storage, and advanced querying capabilities.

## Database Schema

The PostgreSQL implementation uses the following tables:

### Primary Tables

- **maildata**: Primary table storing message metadata and headers
- **maildetail**: Message body content (original and plain text)
- **mailattachments**: Email attachments (stored as BYTEA)
- **audit_log**: Operation tracking and logging

### Key Features

- **Duplicate Detection**: Prevents storing the same message multiple times
- **JSONB Headers**: Full email headers stored as searchable JSON
- **Label Arrays**: Gmail labels stored as PostgreSQL arrays with GIN indexing
- **Attachment Storage**: Binary attachments stored directly in database
- **Audit Trail**: Complete operation logging for compliance

## Usage

### Prerequisites

1. Install PostgreSQL database server
2. Install Python PostgreSQL adapter:
   ```bash
   pip install psycopg2-binary
   ```

### Basic Usage

To backup Gmail messages to PostgreSQL instead of files:

```bash
python3 gyb.py --email user@domain.com \
               --action backup \
               --use-postgres \
               --postgres-host localhost \
               --postgres-port 5432 \
               --postgres-db emailvault \
               --postgres-user gyb_user \
               --postgres-password your_password
```

### Configuration Options

- `--use-postgres`: Enable PostgreSQL storage mode
- `--postgres-host`: Database server hostname (default: localhost)
- `--postgres-port`: Database server port (default: 5432)  
- `--postgres-db`: Database name (default: emailvault)
- `--postgres-user`: Database username (required)
- `--postgres-password`: Database password (required)

### Database Setup

Create a PostgreSQL database and user:

```sql
CREATE DATABASE emailvault;
CREATE USER gyb_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE emailvault TO gyb_user;
```

GYB will automatically create the required tables and indexes on first run.

## Benefits of PostgreSQL Storage

### vs SQLite + Files

- **Scalability**: Better performance with large message volumes
- **Concurrent Access**: Multiple backup processes can run simultaneously
- **Search Capabilities**: Advanced querying with JSONB and full-text search
- **Network Storage**: Centralized storage accessible from multiple servers
- **Backup/Recovery**: Standard PostgreSQL backup tools work seamlessly

### Data Structure

Messages are parsed and stored in structured format:

- Headers as searchable JSONB
- Body content in separate table for efficient retrieval
- Attachments as binary data with metadata
- Labels as PostgreSQL arrays with GIN indexing

### Example Queries

Find messages by sender:
```sql
SELECT "Message-ID", subject, "From" 
FROM maildata 
WHERE "Full Headers"->>'From' LIKE '%@example.com%';
```

Find messages with specific labels:
```sql
SELECT "Message-ID", subject, labels
FROM maildata
WHERE labels && ARRAY['Important', 'Work'];
```

Search message content:
```sql
SELECT m."Message-ID", m.subject, d."Body-PlainText"
FROM maildata m
JOIN maildetail d ON m.vaultid = d.vaultid
WHERE d."Body-PlainText" ILIKE '%project update%';
```

## Backwards Compatibility

- SQLite storage remains the default behavior
- Existing SQLite backups are unaffected
- Use `--use-postgres` flag to opt into PostgreSQL storage
- No migration tool between SQLite and PostgreSQL (yet)

## Performance Considerations

- Initial backup may be slower due to email parsing overhead
- Subsequent incremental backups are faster due to duplicate detection
- Database should have sufficient storage for email attachments
- Consider PostgreSQL tuning for large installations

## Security Notes

- Store database credentials securely
- Use SSL connections in production environments
- Consider database-level encryption for sensitive data
- Audit logs capture all operations for compliance

## Current Limitations

- Restore functionality is partially implemented
- No migration tool from SQLite to PostgreSQL
- Attachment reconstruction needs refinement for complex MIME messages
- Some restore operations may need adjustments for PostgreSQL storage