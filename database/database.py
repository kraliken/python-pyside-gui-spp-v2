import pyodbc
import pandas as pd
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine
from sqlalchemy import text
import urllib


class DatabaseManager:
    def __init__(self, timeout: int = 30):
        load_dotenv()

        self.username = os.getenv("DB_USERNAME")
        self.password = os.getenv("DB_PASSWORD")
        self.server = os.getenv("DB_SERVER")
        self.database = os.getenv("DB_DATABASE")
        self.timeout = timeout

    def raw_connect(self):
        conn_str = (
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server=tcp:{self.server};"
            f"Database={self.database};"
            f"Uid={self.username};Pwd={self.password};"
            f"Encrypt=no;TrustServerCertificate=yes;Connection Timeout={self.timeout};"
        )

        try:
            return pyodbc.connect(conn_str)
        except pyodbc.Error as e:
            error_msg = str(e).lower()
            if "login failed for user" in error_msg:
                raise ValueError("Hibás jelszó.")
            else:
                raise ConnectionError(f"Adatbázis hiba: {e}")

    def connect(self):
        conn_str = (
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server=tcp:{self.server};"
            f"Database={self.database};"
            f"Uid={self.username};Pwd={self.password};"
            f"Encrypt=no;TrustServerCertificate=yes;Connection Timeout={self.timeout};"
        )

        try:
            quoted_conn_str = urllib.parse.quote_plus(conn_str)
            engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}")
            return engine
        except Exception as e:
            raise ConnectionError(f"SQLAlchemy engine létrehozása sikertelen: {e}")

        # try:
        # return pyodbc.connect(conn_str)
        # except pyodbc.Error as e:
        # error_msg = str(e).lower()
        # if "login failed for user" in error_msg:
        # raise ValueError("Hibás jelszó.")
        # else:
        # raise ConnectionError(f"Adatbázis hiba: {e}")

    def query_stage_counts(self) -> dict:
        """Bank/Szállító/Vevő staging táblák sorainak száma egyetlen lekérdezésben.

        A HomeView Stage állapot paneljéhez készült (könnyűsúlyú COUNT query,
        nem tölt be teljes DataFrame-et). pyodbc raw kapcsolatot használ.

        Returns:
            {"bank": int, "vendor": int, "customer": int}
            Kapcsolati hiba esetén mindhárom érték -1
            (a HomeView ezt „—" jelként jeleníti meg).

        Megjegyzés: A HomeView jelenleg hardcoded értékeket használ fejlesztési
        célból. Ez a metódus éles gépen aktiválható — lásd home_view.py
        _load_stage_counts() kommentje.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM dbo.Bank_stage)          AS bank,   "
                "(SELECT COUNT(*) FROM dbo.IremsSzallito_stage) AS vendor, "
                "(SELECT COUNT(*) FROM dbo.IremsVevo_stage)     AS customer"
            )
            row = cursor.fetchone()
            conn.close()
            return {"bank": row[0], "vendor": row[1], "customer": row[2]}
        except Exception:
            return {"bank": -1, "vendor": -1, "customer": -1}

    def query_bank_data(self):

        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql("SELECT * FROM dbo.Bank_stage", conn)
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

        # try:
        # conn = self.connect()
        # df = pd.read_sql("SELECT * FROM dbo.Bank_stage", conn)
        # conn.close()
        # return df
        # except Exception as e:
        # raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def delete_bank_stage(self):

        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dbo.Bank_stage")
            conn.commit()
            conn.close()
            return True, "A Bank_stage tábla adatai sikeresen törölve."
        except Exception as e:
            return False, str(e)

    def insert_bank_rows_bulk(self, df):
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()

                # Fontos: pyodbc gyorsítás
                cursor.fast_executemany = True

                # Minden sort tuple-ként előkészítünk (38 elem)
                values = [
                    tuple(
                        str(row.iloc[i]) if pd.notna(row.iloc[i]) else ""
                        for i in range(38)
                    )
                    for _, row in df.iterrows()
                ]

                # Paraméterként a TVP átadása
                cursor.executemany(
                    "INSERT INTO dbo.Bank_stage VALUES (" + ",".join(["?"] * 38) + ")",
                    values,
                )

                conn.commit()
                return True, "Adatok mentve az adatbázisba."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    # def insert_rows_with_procedure(self, df, procedure="dbo.bank_insert_v1"):
    #     if df.empty:
    #         return False, "Nincs adat a mentéshez."

    #     try:
    #         with self.connect() as conn:
    #             cursor = conn.cursor()

    #             placeholders = ",".join(["?"] * 38)
    #             sql = f"EXEC {procedure} {placeholders}"

    #             for index, row in df.iterrows():
    #                 try:
    #                     values = [
    #                         str(row[i]) if pd.notna(row[i]) else "" for i in range(38)
    #                     ]
    #                     cursor.execute(sql, values)
    #                 except Exception as row_error:
    #                     return (
    #                         False,
    #                         f"Hiba a(z) {index + 1}. sor mentése közben:\n{row_error}",
    #                     )

    #             conn.commit()
    #             return True, "Sikeres feltöltés a tárolt eljáráson keresztül."

    #     except ValueError as ve:
    #         return False, str(ve)
    #     except ConnectionError as ce:
    #         return False, str(ce)
    #     except Exception as e:
    #         return False, f"Általános hiba a mentés során: {e}"

    def query_vendor_data(self):

        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql("SELECT * FROM dbo.IremsSzallito_stage", conn)
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

        # try:
        # conn = self.connect()
        # df = pd.read_sql("SELECT * FROM dbo.IremsSzallito_stage", conn)
        # conn.close()
        # return df
        # except Exception as e:
        # raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def delete_vendor_stage(self):
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dbo.IremsSzallito_stage")
            conn.commit()
            conn.close()
            return True, "Az IremsSzallito_stage tábla adatai sikeresen törölve."
        except Exception as e:
            return False, str(e)

    def insert_vendor_rows_bulk(self, df):
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()

                # Fontos: pyodbc gyorsítás
                cursor.fast_executemany = True

                # Minden sort tuple-ként előkészítünk (38 elem)
                values = [
                    tuple(
                        # str(row.iloc[i]) if pd.notna(row.iloc[i]) else ""
                        None if pd.isna(row.iloc[i]) else str(row.iloc[i])
                        for i in range(9)
                    )
                    for _, row in df.iterrows()
                ]

                # print(values)

                # Paraméterként a TVP átadása
                cursor.executemany(
                    "INSERT INTO dbo.IremsSzallito_stage VALUES ("
                    + ",".join(["?"] * 9)
                    + ")",
                    values,
                )

                # # Explicit módon megadjuk az oszlopneveket, kihagyva az ID-t, ami valószínűleg automatikusan generált
                # cursor.executemany(
                #     "INSERT INTO dbo.IremsSzallito_stage (Column1, Column2, Column3, Column4, Column5, Column6, Column7, Column8, Column9) VALUES ("
                #     + ",".join(["?"] * 9)
                #     + ")",
                #     values,
                # )

                conn.commit()
                return True, "Adatok mentve az adatbázisba."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    def query_customer_data(self):
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql("SELECT * FROM dbo.IremsVevo_stage", conn)
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

        # try:
        # conn = self.connect()
        # df = pd.read_sql("SELECT * FROM dbo.IremsVevo_stage", conn)
        # conn.close()
        # return df
        # except Exception as e:
        # raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def delete_customer_stage(self):
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dbo.IremsVevo_stage")
            conn.commit()
            conn.close()
            return True, "Az IremsVevo_stage tábla adatai sikeresen törölve."
        except Exception as e:
            return False, str(e)

    def insert_customer_rows_bulk(self, df):
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()

                # Fontos: pyodbc gyorsítás
                cursor.fast_executemany = True

                # Minden sort tuple-ként előkészítünk (38 elem)
                values = [
                    tuple(
                        # str(row.iloc[i]) if pd.notna(row.iloc[i]) else ""
                        None if pd.isna(row.iloc[i]) else str(row.iloc[i])
                        for i in range(9)
                    )
                    for _, row in df.iterrows()
                ]

                # Paraméterként a TVP átadása
                cursor.executemany(
                    "INSERT INTO dbo.IremsVevo_stage VALUES ("
                    + ",".join(["?"] * 9)
                    + ")",
                    values,
                )

                conn.commit()
                return True, "Adatok mentve az adatbázisba."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    def call_vendor_insert1(self, date):
        """Szállító staging → Hist tárolt eljárás hívása dátum paraméterrel.

        Args:
            date: str formátumban "YYYY-MM-DD" — a könyvelési dátum, amelyet
                  a tárolt eljárás @datum DATE paraméterként vár.

        Megjegyzés (SQL Server oldal): A dbo.szallito_insert1 tárolt eljárást
        módosítani kell: fogadjon @datum DATE paramétert, és szűrjön/jelöljön
        erre a dátumra a staging → Hist mozgatás során.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("{CALL dbo.szallito_insert1(?)}", (date,))
            conn.commit()
            conn.close()
            return True, "Az IremsSzallito_Stage adatai mentve az Irems_Hist táblába."

        except Exception as e:
            return False, str(e)

    def call_customer_insert1(self, date):
        """Vevő staging → Hist tárolt eljárás hívása dátum paraméterrel.

        Args:
            date: str formátumban "YYYY-MM-DD" — a könyvelési dátum, amelyet
                  a tárolt eljárás @datum DATE paraméterként vár.

        Megjegyzés (SQL Server oldal): A dbo.vevo_insert1 tárolt eljárást
        módosítani kell: fogadjon @datum DATE paramétert, és szűrjön/jelöljön
        erre a dátumra a staging → Hist mozgatás során.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("{CALL dbo.vevo_insert1(?)}", (date,))
            conn.commit()
            conn.close()
            return True, "Az IremsVevo_Stage adatai mentve az Irems_Hist táblába."

        except Exception as e:
            return False, str(e)

    def call_bank_insert1(self):
        """Bank staging → Hist tárolt eljárás hívása dátum paraméterrel.

        Megjegyzés (SQL Server oldal): A dbo.bank_insert1 tárolt eljárást
        módosítani kell: fogadjon @datum DATE paramétert, és szűrjön/jelöljön
        erre a dátumra a staging → Hist mozgatás során.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("{CALL dbo.bank_insert1}")
            conn.commit()
            conn.close()
            return True, "Az Bank_Stage adatai mentve az Bank_Hist táblába."

        except Exception as e:
            return False, str(e)

    def query_bank_account_numbers(self) -> pd.DataFrame:
        """Bankszámlaszám törzsadatok lekérdezése (dbo.Bankszamlaszam_torzs)."""
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql(
                    "SELECT ID, Bankszamlaszam, Bankszamlaszam_fokonyv, "
                    "Bankszamlaszam_deviza, Bankszamlaszam_tipus, Partner "
                    "FROM dbo.Bankszamlaszam_torzs ORDER BY ID",
                    conn,
                )
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def query_bank_internal_codes(self) -> pd.DataFrame:
        """Bank belső kód törzsadatok lekérdezése (dbo.Bank_belsokod)."""
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql(
                    "SELECT ID, Belsokod, Fokony, FokonyvText "
                    "FROM dbo.Bank_belsokod ORDER BY ID",
                    conn,
                )
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def query_partner_mapping(self) -> pd.DataFrame:
        """Partner mapping törzsadatok lekérdezése (dbo.Partner_mapping)."""
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql(
                    "SELECT ID, UMS_parnter, Combosoft_partner "
                    "FROM dbo.Partner_mapping ORDER BY ID",
                    conn,
                )
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def insert_bank_account_number_rows_bulk(self, df):
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()
                cursor.fast_executemany = True

                values = [
                    tuple(
                        "" if pd.isna(row[col]) else str(row[col])
                        for col in [
                            "Bankszamlaszam",
                            "Bankszamlaszam_fokonyv",
                            "Bankszamlaszam_deviza",
                            "Bankszamlaszam_tipus",
                        ]
                    )
                    for _, row in df.iterrows()
                ]

                # A tábla ID oszlopa auto-increment, ezért nem szerepel az insert-ben
                cursor.executemany(
                    """
                    INSERT INTO dbo.Bankszamlaszam_torzs
                    (Bankszamlaszam, Bankszamlaszam_fokonyv, Bankszamlaszam_deviza, Bankszamlaszam_tipus)
                    VALUES (?, ?, ?, ?)
                    """,
                    values,
                )

                conn.commit()
                return True, "Bankszámlaszám adatok sikeresen elmentve."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    def insert_bank_internal_code_rows_bulk(self, df):
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()
                cursor.fast_executemany = True

                values = [
                    tuple(
                        "" if pd.isna(row[col]) else str(row[col])
                        for col in [
                            "Belsokod",
                            "Fokony",
                            "FokonyvText",
                        ]
                    )
                    for _, row in df.iterrows()
                ]

                # A tábla ID oszlopa auto-increment, ezért nem szerepel az insert-ben
                cursor.executemany(
                    """
                    INSERT INTO dbo.Bank_belsokod
                    (Belsokod, Fokony, FokonyvText)
                    VALUES (?, ?, ?)
                    """,
                    values,
                )

                conn.commit()
                return True, "Bank belső kódok sikeresen elmentve."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    # def insert_rows_with_procedure(self, df, password, procedure="dbo.bank_insert_v1"):
    #     conn = None
    #     try:
    #         conn = self.connect(password)
    #         cursor = conn.cursor()

    #         for index, row in df.iterrows():
    #             values = [str(row[i]) if pd.notna(row[i]) else "" for i in range(38)]
    #             placeholders = ",".join(["?"] * 38)
    #             sql = f"EXEC {procedure} {placeholders}"
    #             cursor.execute(sql, values)

    #         conn.commit()
    #         return True, "Sikeres feltöltés a tárolt eljáráson keresztül."
    #     except Exception as e:
    #         return False, f"Hiba a feltöltés során: {e}"
    #     finally:
    #         if conn:
    #             conn.close()
