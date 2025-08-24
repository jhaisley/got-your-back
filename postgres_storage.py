#!/usr/bin/env python3
"""
PostgreSQL storage backend for Got Your Back (GYB)

This module provides PostgreSQL database storage functionality for email backup,
separating PostgreSQL-specific code from the main gyb.py file to minimize
changes to the core application.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from email.message import EmailMessage
import email.utils

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


class PostgreSQLConfig:
    """Configuration management for PostgreSQL connection using .env files"""
    
    def __init__(self):
        if DOTENV_AVAILABLE:
            load_dotenv()
        
        self.host = os.getenv('VAULT_DB_HOST', 'localhost')
        self.port = int(os.getenv('VAULT_DB_PORT', '5432'))
        self.database = os.getenv('VAULT_DB_NAME', 'emailvault')
        self.user = os.getenv('VAULT_DB_USER', '')
        self.password = os.getenv('VAULT_DB_PASS', '')
        
    def get_connection_string(self) -> str:
        """Generate PostgreSQL connection string"""
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"
    
    def is_configured(self) -> bool:
        """Check if all required configuration is present"""
        return bool(self.user and self.password)


class PostgreSQLStorage:
    """PostgreSQL storage backend for email messages"""
    
    def __init__(self, config: PostgreSQLConfig):
        if not PSYCOPG_AVAILABLE:
            raise ImportError("psycopg is required for PostgreSQL support. Install with: pip install psycopg[binary]")
        
        self.config = config
        self.connection = None
        
    def connect(self):
        """Establish connection to PostgreSQL database"""
        if not self.config.is_configured():
            raise ValueError("PostgreSQL database credentials not configured. Check .env file.")
            
        try:
            self.connection = psycopg.connect(
                self.config.get_connection_string(),
                row_factory=dict_row
            )
            self.connection.autocommit = True
            return True
        except Exception as e:
            print(f"Failed to connect to PostgreSQL: {e}")
            return False
    
    def disconnect(self):
        """Close PostgreSQL connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def create_schema(self):
        """Create Email-Vault database schema"""
        schema_sql = """
        -- Create audit_log table first (no dependencies)
        CREATE TABLE IF NOT EXISTS audit_log (
            logid SERIAL PRIMARY KEY,
            userid VARCHAR(255),
            operation VARCHAR(50),
            object_type VARCHAR(50),
            object_id VARCHAR(255),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details JSONB
        );

        -- Create settings table (no dependencies)
        CREATE TABLE IF NOT EXISTS settings (
            settingid SERIAL PRIMARY KEY,
            section VARCHAR(100) NOT NULL,
            option VARCHAR(100) NOT NULL,
            value TEXT,
            UNIQUE(section, option)
        );

        -- Create maildata table (main email metadata)
        CREATE TABLE IF NOT EXISTS maildata (
            vaultid SERIAL PRIMARY KEY,
            "Message-ID" VARCHAR(255),
            "Thread-ID" VARCHAR(255),
            "X-GM-THRID" VARCHAR(255),
            "X-GM-MSGID" VARCHAR(255),
            "X-Gmail-Labels" TEXT[],
            "Date" TIMESTAMP,
            "From" TEXT,
            "To" TEXT,
            "Cc" TEXT,
            "Bcc" TEXT,
            "Subject" TEXT,
            "Original-File" VARCHAR(500),
            mboxusername VARCHAR(255),
            headers JSONB,
            rfc822_size INTEGER,
            backup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            has_attachments BOOLEAN DEFAULT FALSE,
            attachment_count INTEGER DEFAULT 0
        );

        -- Create maildetail table (message body content)
        CREATE TABLE IF NOT EXISTS maildetail (
            detailid SERIAL PRIMARY KEY,
            vaultid INTEGER REFERENCES maildata(vaultid) ON DELETE CASCADE,
            content_type VARCHAR(100),
            content_html TEXT,
            content_text TEXT,
            content_raw BYTEA
        );

        -- Create mailattachments table (binary attachments)
        CREATE TABLE IF NOT EXISTS mailattachments (
            attachmentid SERIAL PRIMARY KEY,
            vaultid INTEGER REFERENCES maildata(vaultid) ON DELETE CASCADE,
            filename VARCHAR(500),
            content_type VARCHAR(200),
            content_size INTEGER,
            content_data BYTEA,
            attachment_order INTEGER DEFAULT 0
        );

        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_maildata_messageid ON maildata("Message-ID");
        CREATE INDEX IF NOT EXISTS idx_maildata_threadid ON maildata("Thread-ID");
        CREATE INDEX IF NOT EXISTS idx_maildata_gmthrid ON maildata("X-GM-THRID");
        CREATE INDEX IF NOT EXISTS idx_maildata_gmmsgid ON maildata("X-GM-MSGID");
        CREATE INDEX IF NOT EXISTS idx_maildata_date ON maildata("Date");
        CREATE INDEX IF NOT EXISTS idx_maildata_mboxusername ON maildata(mboxusername);
        CREATE INDEX IF NOT EXISTS idx_maildata_originalfile ON maildata("Original-File");
        CREATE INDEX IF NOT EXISTS idx_maildata_labels ON maildata USING GIN("X-Gmail-Labels");
        CREATE INDEX IF NOT EXISTS idx_maildata_headers ON maildata USING GIN(headers);
        CREATE INDEX IF NOT EXISTS idx_maildetail_vaultid ON maildetail(vaultid);
        CREATE INDEX IF NOT EXISTS idx_mailattachments_vaultid ON mailattachments(vaultid);
        CREATE INDEX IF NOT EXISTS idx_audit_log_userid ON audit_log(userid);
        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(schema_sql)
            self._log_audit('system', 'schema_creation', 'database', 'email_vault', {'status': 'success'})
            return True
        except Exception as e:
            print(f"Failed to create database schema: {e}")
            return False
    
    def check_duplicate(self, message_id: str, mbox_username: str, original_file: str) -> Optional[int]:
        """Check for duplicate message using specified logic"""
        sql = '''
        SELECT vaultid FROM maildata 
        WHERE "Message-ID" = %s AND mboxusername = %s AND "Original-File" = %s
        '''
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, (message_id, mbox_username, original_file))
                result = cursor.fetchone()
                return result['vaultid'] if result else None
        except Exception as e:
            print(f"Error checking for duplicate: {e}")
            return None
    
    def parse_email_message(self, raw_message: bytes) -> Dict[str, Any]:
        """Parse raw email message and extract components"""
        try:
            msg = email.message_from_bytes(raw_message)
            
            # Extract headers
            headers = {}
            for key, value in msg.items():
                if key in headers:
                    if isinstance(headers[key], list):
                        headers[key].append(value)
                    else:
                        headers[key] = [headers[key], value]
                else:
                    headers[key] = value
            
            # Extract body content
            content_html = ""
            content_text = ""
            attachments = []
            
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition", ""))
                    
                    if "attachment" in content_disposition:
                        # Handle attachment
                        filename = part.get_filename()
                        if filename:
                            attachments.append({
                                'filename': filename,
                                'content_type': content_type,
                                'content_data': part.get_payload(decode=True),
                                'content_size': len(part.get_payload(decode=True)) if part.get_payload(decode=True) else 0
                            })
                    elif content_type == "text/plain" and not content_text:
                        content_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif content_type == "text/html" and not content_html:
                        content_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            else:
                # Single part message
                content_type = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                if payload:
                    content = payload.decode('utf-8', errors='ignore')
                    if content_type == "text/html":
                        content_html = content
                    else:
                        content_text = content
            
            return {
                'headers': headers,
                'content_html': content_html,
                'content_text': content_text,
                'attachments': attachments,
                'rfc822_size': len(raw_message)
            }
            
        except Exception as e:
            print(f"Error parsing email message: {e}")
            return None
    
    def store_message(self, raw_message: bytes, message_id: str, thread_id: str, 
                     gmail_thread_id: str, gmail_message_id: str, labels: List[str],
                     mbox_username: str, original_file: str) -> Optional[int]:
        """Store email message in PostgreSQL database"""
        
        # Parse the email message
        parsed = self.parse_email_message(raw_message)
        if not parsed:
            return None
        
        try:
            with self.connection.cursor() as cursor:
                # Insert main message data
                insert_sql = '''
                INSERT INTO maildata (
                    "Message-ID", "Thread-ID", "X-GM-THRID", "X-GM-MSGID",
                    "X-Gmail-Labels", "Date", "From", "To", "Cc", "Bcc", "Subject",
                    "Original-File", mboxusername, headers, rfc822_size,
                    has_attachments, attachment_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING vaultid
                '''
                
                headers = parsed['headers']
                date_str = headers.get('Date', '')
                date_parsed = None
                if date_str:
                    try:
                        date_parsed = email.utils.parsedate_to_datetime(date_str)
                    except:
                        pass
                
                cursor.execute(insert_sql, (
                    message_id, thread_id, gmail_thread_id, gmail_message_id,
                    labels, date_parsed, headers.get('From', ''), headers.get('To', ''),
                    headers.get('Cc', ''), headers.get('Bcc', ''), headers.get('Subject', ''),
                    original_file, mbox_username, json.dumps(headers), parsed['rfc822_size'],
                    len(parsed['attachments']) > 0, len(parsed['attachments'])
                ))
                
                result = cursor.fetchone()
                vault_id = result['vaultid']
                
                # Insert message content
                detail_sql = '''
                INSERT INTO maildetail (vaultid, content_type, content_html, content_text, content_raw)
                VALUES (%s, %s, %s, %s, %s)
                '''
                cursor.execute(detail_sql, (
                    vault_id, 'text/html', parsed['content_html'], 
                    parsed['content_text'], raw_message
                ))
                
                # Insert attachments
                for i, attachment in enumerate(parsed['attachments']):
                    attach_sql = '''
                    INSERT INTO mailattachments (vaultid, filename, content_type, content_size, content_data, attachment_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    '''
                    cursor.execute(attach_sql, (
                        vault_id, attachment['filename'], attachment['content_type'],
                        attachment['content_size'], attachment['content_data'], i
                    ))
                
                # Log the operation
                self._log_audit(mbox_username, 'store_message', 'maildata', str(vault_id), {
                    'message_id': message_id,
                    'original_file': original_file,
                    'attachment_count': len(parsed['attachments'])
                })
                
                return vault_id
                
        except Exception as e:
            print(f"Error storing message: {e}")
            return None
    
    def _log_audit(self, userid: str, operation: str, object_type: str, object_id: str, details: Dict):
        """Log operation to audit trail"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO audit_log (userid, operation, object_type, object_id, details)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (userid, operation, object_type, object_id, json.dumps(details)))
        except Exception as e:
            print(f"Warning: Failed to log audit entry: {e}")
    
    def get_message_count(self, mbox_username: str) -> int:
        """Get total number of messages for a user"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) as count FROM maildata WHERE mboxusername = %s', (mbox_username,))
                result = cursor.fetchone()
                return result['count'] if result else 0
        except Exception as e:
            print(f"Error getting message count: {e}")
            return 0
    
    def get_settings(self) -> Dict[str, Dict[str, str]]:
        """Retrieve settings from database"""
        settings = {}
        try:
            with self.connection.cursor() as cursor:
                cursor.execute('SELECT section, option, value FROM settings')
                results = cursor.fetchall()
                for row in results:
                    section = row['section']
                    if section not in settings:
                        settings[section] = {}
                    settings[section][row['option']] = row['value']
        except Exception as e:
            print(f"Error retrieving settings: {e}")
        return settings
    
    def set_setting(self, section: str, option: str, value: str):
        """Store setting in database"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO settings (section, option, value) 
                    VALUES (%s, %s, %s)
                    ON CONFLICT (section, option) 
                    DO UPDATE SET value = EXCLUDED.value
                ''', (section, option, value))
        except Exception as e:
            print(f"Error storing setting: {e}")


def create_postgres_storage() -> Optional[PostgreSQLStorage]:
    """Factory function to create PostgreSQL storage instance"""
    config = PostgreSQLConfig()
    
    if not config.is_configured():
        print("PostgreSQL configuration not found. Please check your .env file.")
        return None
    
    storage = PostgreSQLStorage(config)
    if storage.connect():
        if storage.create_schema():
            return storage
        else:
            storage.disconnect()
    
    return None


def is_postgres_available() -> bool:
    """Check if PostgreSQL dependencies are available"""
    return PSYCOPG_AVAILABLE and DOTENV_AVAILABLE