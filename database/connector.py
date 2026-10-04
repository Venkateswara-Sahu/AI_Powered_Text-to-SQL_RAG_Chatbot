import mysql.connector
from mysql.connector import pooling, Error
from config import Config
from database.sql_policy import prepare_read_query, validate_read_query


class DatabaseConnector:
    """Manages MySQL connection pool and safe query execution."""

    def __init__(self):
        """Initialize MySQL connection pool."""
        try:
            pool_config = {
                "pool_name": "f1db_pool",
                "pool_size": 5,
                "pool_reset_session": True,
                "host": Config.MYSQL_HOST,
                "port": Config.MYSQL_PORT,
                "user": Config.MYSQL_USER,
                "password": Config.MYSQL_PASSWORD,
                "database": Config.MYSQL_DATABASE,
                "charset": "utf8mb4",
                "use_unicode": True,
            }

            # TiDB Cloud requires SSL/TLS
            if Config.MYSQL_SSL:
                pool_config.update(self._tls_options())

            self.pool = pooling.MySQLConnectionPool(**pool_config)
            print(f"[DB] Connected to MySQL ({Config.MYSQL_HOST}:{Config.MYSQL_PORT}/{Config.MYSQL_DATABASE})")
        except Error as e:
            print(f"[DB] Connection failed: {e}")
            raise

    def get_connection(self):
        """Get a connection from pool, with fallback to fresh connection on stale pool."""
        try:
            return self.pool.get_connection()
        except Error:
            # Pool connection stale — create fresh direct connection
            connect_args = {
                "host": Config.MYSQL_HOST,
                "port": Config.MYSQL_PORT,
                "user": Config.MYSQL_USER,
                "password": Config.MYSQL_PASSWORD,
                "database": Config.MYSQL_DATABASE,
                "charset": "utf8mb4",
                "use_unicode": True,
            }
            if Config.MYSQL_SSL:
                connect_args.update(self._tls_options())
            return mysql.connector.connect(**connect_args)

    def _is_safe_query(self, sql: str) -> bool:
        """Apply the same parsed-query policy used by the agent."""
        return validate_read_query(sql)[0]

    @staticmethod
    def _tls_options() -> dict:
        return {"ssl_ca": Config.MYSQL_SSL_CA,
                "ssl_verify_cert": True, "ssl_verify_identity": True}

    def execute_query(self, sql: str, limit: int = 50) -> dict:
        """
        Execute a read-only SQL query and return results.

        Returns:
            dict with keys: success, columns, rows, row_count, error
        """
        try:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
                raise ValueError("The row limit must be a positive integer.")
            row_limit = min(limit, Config.SQL_MAX_ROWS)
            cleaned = prepare_read_query(sql, row_limit)
        except ValueError as exc:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": f"Query blocked: {exc}"
            }

        connection = None
        cursor = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(cleaned)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            # Convert non-serializable types to strings
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, (bytes, bytearray)):
                        row[key] = "<binary data>"
                    elif hasattr(value, "isoformat"):
                        row[key] = value.isoformat()
                    elif value is not None and not isinstance(value, (str, int, float, bool)):
                        row[key] = str(value)

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "error": None,
                "executed_sql": cleaned,
                "row_limit": row_limit,
            }
        except Error as e:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": str(e)
            }
        finally:
            if cursor:
                try:
                    cursor.close()
                except Error:
                    pass
            if connection:
                try:
                    connection.close()
                except Exception:
                    pass

    def get_schema_info(self) -> list[dict]:
        """
        Retrieve full schema metadata from INFORMATION_SCHEMA.
        Returns a list of table info dicts with columns, types, keys, and sample data.
        """
        connection = None
        try:
            connection = self.pool.get_connection()
            cursor = connection.cursor(dictionary=True)

            # Get all tables
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """, (Config.MYSQL_DATABASE,))
            tables = cursor.fetchall()

            schema_info = []
            for table in tables:
                table_name = table["TABLE_NAME"]

                # Get columns for this table
                cursor.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY,
                           COLUMN_DEFAULT, COLUMN_COMMENT, CHARACTER_MAXIMUM_LENGTH
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                """, (Config.MYSQL_DATABASE, table_name))
                columns = cursor.fetchall()

                # Get foreign keys
                cursor.execute("""
                    SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                      AND REFERENCED_TABLE_NAME IS NOT NULL
                """, (Config.MYSQL_DATABASE, table_name))
                foreign_keys = cursor.fetchall()

                # Get sample rows (first 3)
                try:
                    cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 3")
                    sample_rows = cursor.fetchall()
                    # Clean binary data from samples
                    for row in sample_rows:
                        for key, value in row.items():
                            if isinstance(value, (bytes, bytearray)):
                                row[key] = "<binary>"
                            elif hasattr(value, "isoformat"):
                                row[key] = value.isoformat()
                except Exception:
                    sample_rows = []

                # Get row count
                cursor.execute(f"SELECT COUNT(*) as cnt FROM `{table_name}`")
                row_count = cursor.fetchone()["cnt"]

                schema_info.append({
                    "table_name": table_name,
                    "table_comment": table.get("TABLE_COMMENT", ""),
                    "row_count": row_count,
                    "columns": columns,
                    "foreign_keys": foreign_keys,
                    "sample_rows": sample_rows,
                })

            return schema_info

        except Error as e:
            print(f"[DB] Schema retrieval failed: {e}")
            return []
        finally:
            if connection:
                connection.close()

    def test_connection(self) -> bool:
        """Test if the database connection is working."""
        try:
            result = self.execute_query("SELECT 1 AS test")
            return result["success"]
        except Exception:
            return False
