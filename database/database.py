# database/database.py
#
# DatabaseManager — Az összes SQL Server adatbázis-művelet egy helyen.
#
# Ez az osztály felelős minden adatbázis-kommunikációért:
#   - Kapcsolatok kezelése (pyodbc raw + SQLAlchemy engine)
#   - SELECT lekérdezések pandas DataFrame-ként
#   - INSERT (bulk) a staging táblákba
#   - DELETE a staging táblákból
#   - Tárolt eljárások hívása (CALL)
#   - CRUD műveletek a törzsadattáblákhoz (bankszámlaszám, belső kód, partner)
#
# Két kapcsolat típus:
#   raw_connect() → pyodbc.Connection: direkt SQL, DELETE, CALL, egyedi INSERT
#   connect()     → SQLAlchemy Engine: pandas read_sql() kompatibilis, bulk INSERT
#
# Kapcsolat adatok: .env fájlból töltődnek be (python-dotenv)
# .env szükséges mezők: DB_USERNAME, DB_PASSWORD, DB_SERVER, DB_DATABASE

import pyodbc     # Microsoft SQL Server ODBC kapcsolat (ODBC Driver 17 szükséges)
import pandas as pd  # SELECT eredmények DataFrame formában
from dotenv import load_dotenv  # .env fájl betöltése (jelszavak, kapcsolati adatok)
import os
from sqlalchemy import create_engine  # SQLAlchemy engine (pandas read_sql()-hoz)
from sqlalchemy import text           # (importálva, de jelenleg nem használt direkten)
import urllib                         # Connection string URL-kódoláshoz (SQLAlchemy-hoz)


class DatabaseManager:
    """SQL Server adatbázis-kezelő osztály.

    Minden SQL Server művelet ezen az osztályon keresztül zajlik.
    Minden nézet saját példányt hoz létre belőle (__init__-ben: self.db = DatabaseManager()).
    """

    def __init__(self, timeout: int = 30):
        """Kapcsolati adatok betöltése a .env fájlból.

        Args:
            timeout: kapcsolódási időtúllépés másodpercben (alapértelmezett: 30)
        """
        load_dotenv()  # .env fájl betöltése a munkakönyvtárból (vagy szülő könyvtárból)

        # Környezeti változók olvasása (None, ha nincs megadva)
        self.username = os.getenv("DB_USERNAME")
        self.password = os.getenv("DB_PASSWORD")
        self.server = os.getenv("DB_SERVER")       # pl. "172.16.0.16\Maxoft"
        self.database = os.getenv("DB_DATABASE")   # pl. "Developer_db"
        self.timeout = timeout

    def raw_connect(self):
        """Közvetlen pyodbc kapcsolat létrehozása az SQL Serverhez.

        Mikor használjuk: DELETE, egyedi INSERT, tárolt eljárás (CALL), CRUD.
        A pyodbc kapcsolat közvetlenül kommunikál az ODBC driverrel — gyorsabb,
        és lehetővé teszi a fast_executemany optimalizációt bulk INSERT-nél.

        Returns:
            pyodbc.Connection: aktív DB kapcsolat

        Raises:
            ValueError: ha a bejelentkezési adatok hibásak
            ConnectionError: egyéb kapcsolódási hiba esetén
        """
        conn_str = (
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            # f"Server=tcp:{self.server};"  # tcp: prefix named instance-nél nem működik
            f"Server={self.server};"
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
        """SQLAlchemy engine létrehozása az SQL Serverhez.

        Mikor használjuk: SELECT lekérdezések pd.read_sql()-lel.
        A pandas read_sql() SQLAlchemy engine-t vagy Connection-t vár —
        a pyodbc kapcsolat közvetlenül nem kompatibilis ezzel a pandas API-val.

        A connection string URL-kódolással kerül át az SQLAlchemy-nak:
        urllib.parse.quote_plus() a pontosvesszőket és speciális karaktereket kódolja.

        Returns:
            sqlalchemy.Engine: konfigurált motor (nem aktív kapcsolat!)

        Raises:
            ConnectionError: ha az engine létrehozása sikertelen
        """
        conn_str = (
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            # f"Server=tcp:{self.server};"
            f"Server={self.server};"
            f"Database={self.database};"
            f"Uid={self.username};Pwd={self.password};"
            f"Encrypt=no;TrustServerCertificate=yes;Connection Timeout={self.timeout};"
        )

        try:
            # Az ODBC connection string URL-kódolva átadása az SQLAlchemy-nak
            quoted_conn_str = urllib.parse.quote_plus(conn_str)
            engine = create_engine(f"mssql+pyodbc:///?odbc_connect={quoted_conn_str}")
            return engine
        except Exception as e:
            raise ConnectionError(f"SQLAlchemy engine létrehozása sikertelen: {e}")

        # Régi pyodbc közvetlen mód (kikommentelve, SQLAlchemy váltotta fel):
        # try:
        # return pyodbc.connect(conn_str)
        # except pyodbc.Error as e:
        # error_msg = str(e).lower()
        # if "login failed for user" in error_msg:
        # raise ValueError("Hibás jelszó.")
        # else:
        # raise ConnectionError(f"Adatbázis hiba: {e}")

    # =========================================================================
    # Kezdőlap statisztika
    # =========================================================================

    def query_stage_counts(self) -> dict:
        """Bank/Szállító/Vevő staging táblák sorainak száma egyetlen lekérdezésben.

        A HomeView Stage állapot paneljéhez készült (könnyűsúlyú COUNT query,
        nem tölt be teljes DataFrame-et). pyodbc raw kapcsolatot használ.

        Returns:
            {"bank": int, "vendor": int, "customer": int}
            Kapcsolati hiba esetén mindhárom érték -1
            (a HomeView ezt "—" jelként jeleníti meg).

        Megjegyzés: A HomeView jelenleg hardcoded értékeket használ fejlesztési
        célból. Ez a metódus éles gépen aktiválható — lásd home_view.py
        _load_stage_counts() kommentje.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            # Egyetlen SELECT-tel lekérdezi mindhárom tábla sorszámát
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

    # =========================================================================
    # Bank staging tábla (dbo.Bank_stage — 38 oszlop)
    # =========================================================================

    def query_bank_data(self):
        """Bank staging tábla összes sorának lekérdezése DataFrame-ként.

        SQLAlchemy engine-t használ (pandas read_sql() kompatibilitás miatt).
        """
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql("SELECT * FROM dbo.Bank_stage", conn)
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

        # Régi közvetlen pyodbc mód (kikommentelve):
        # try:
        # conn = self.connect()
        # df = pd.read_sql("SELECT * FROM dbo.Bank_stage", conn)
        # conn.close()
        # return df
        # except Exception as e:
        # raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def delete_bank_stage(self):
        """Bank staging tábla teljes tartalmának törlése.

        Returns:
            (True, üzenet) siker esetén, (False, hibaüzenet) hiba esetén
        """
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
        """Bank staging táblába tömeges INSERT (bulk insert).

        Optimalizáció: cursor.fast_executemany = True — a pyodbc egyszerre
        elküldi az összes sort a szervernek (nem egyenként), ami ~10-100x gyorsabb.

        Args:
            df: pandas DataFrame 38 oszloppal (Column1..Column38)

        A DataFrame sorait tuple listává alakítja, ahol minden elem string (vagy üres string).
        None értékek helyett üres string kerül (SQL Server VARCHAR kompatibilitás).
        """
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()

                # fast_executemany: bulk optimalizáció — az összes sor egy hálózati kérésben
                cursor.fast_executemany = True

                # DataFrame sorok → tuple lista (38 elem/sor)
                values = [
                    tuple(
                        str(row.iloc[i]) if pd.notna(row.iloc[i]) else ""
                        for i in range(38)
                    )
                    for _, row in df.iterrows()
                ]

                # 38 paraméterhelyes INSERT (? = pyodbc paraméter-jelölő)
                cursor.executemany(
                    "INSERT INTO dbo.Bank_stage VALUES (" + ",".join(["?"] * 38) + ")",
                    values,
                )

                conn.commit()
                return True, "Adatok mentve az adatbázisba."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    # Tárolt eljárásos INSERT — régi megközelítés (kikommentelve):
    # def insert_rows_with_procedure(self, df, procedure="dbo.bank_insert_v1"):
    #     ...

    # =========================================================================
    # Szállítói staging tábla (dbo.IremsSzallito_stage — 9 oszlop)
    # =========================================================================

    def query_vendor_data(self):
        """Szállítói staging tábla lekérdezése DataFrame-ként."""
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql("SELECT * FROM dbo.IremsSzallito_stage", conn)
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def delete_vendor_stage(self):
        """Szállítói staging tábla teljes törlése."""
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
        """Szállítói staging táblába tömeges INSERT (9 oszlop).

        Különbség a banki bulk insert-hez képest:
          - Csak 9 oszlop (nem 38)
          - None értékeket megtartja (pd.isna check: None → SQL NULL)
            A szállítói táblában engedélyezett a NULL (ellentétben a banki VARCHAR mezőkkel)
        """
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()
                cursor.fast_executemany = True

                # None ha NaN (SQL NULL), str ha van érték
                values = [
                    tuple(
                        None if pd.isna(row.iloc[i]) else str(row.iloc[i])
                        for i in range(9)
                    )
                    for _, row in df.iterrows()
                ]

                cursor.executemany(
                    "INSERT INTO dbo.IremsSzallito_stage VALUES ("
                    + ",".join(["?"] * 9)
                    + ")",
                    values,
                )

                conn.commit()
                return True, "Adatok mentve az adatbázisba."

        except Exception as e:
            return False, f"Hiba a mentés során: {e}"

    # =========================================================================
    # Vevői staging tábla (dbo.IremsVevo_stage — 9 oszlop)
    # =========================================================================

    def query_customer_data(self):
        """Vevői staging tábla lekérdezése DataFrame-ként."""
        try:
            engine = self.connect()
            with engine.connect() as conn:
                df = pd.read_sql("SELECT * FROM dbo.IremsVevo_stage", conn)
            return df
        except Exception as e:
            raise RuntimeError(f"Hiba a lekérdezés során: {e}")

    def delete_customer_stage(self):
        """Vevői staging tábla teljes törlése."""
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
        """Vevői staging táblába tömeges INSERT (9 oszlop).

        A szállítói bulk inserttel azonos logika — None → SQL NULL megtartva.
        """
        if df.empty:
            return False, "Nincs adat a mentéshez."

        try:
            with self.raw_connect() as conn:
                cursor = conn.cursor()
                cursor.fast_executemany = True

                values = [
                    tuple(
                        None if pd.isna(row.iloc[i]) else str(row.iloc[i])
                        for i in range(9)
                    )
                    for _, row in df.iterrows()
                ]

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

    # =========================================================================
    # Tárolt eljárások (staging → Hist áthelyezés)
    # =========================================================================

    def call_vendor_insert1(self, date):
        """Szállítói staging → Hist tárolt eljárás hívása dátum paraméterrel.

        Args:
            date: str formátumban "YYYY-MM-DD" — a könyvelési dátum,
                  amelyet a dbo.szallito_insert1 eljárás @datum paraméterként vár.

        A pyodbc ODBC escape szintaxis: {CALL eljárás(?)} — ez a szabványos
        ODBC módja a tárolt eljárás paraméteres hívásának.
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
        """Vevői staging → Hist tárolt eljárás hívása dátum paraméterrel.

        Args:
            date: str formátumban "YYYY-MM-DD" — a dbo.vevo_insert1 eljárás @datum paramétere.
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
        """Bank staging → Hist tárolt eljárás hívása (dátum paraméter nélkül).

        Megjegyzés: a bank_insert1 eljárás jelenleg nem fogad dátum paramétert
        (ellentétben a szállítói/vevői változattal). Jövőbeli fejlesztés során
        érdemes egységesíteni.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("{CALL dbo.bank_insert1}")  # paraméter nélküli hívás
            conn.commit()
            conn.close()
            return True, "Az Bank_Stage adatai mentve az Bank_Hist táblába."
        except Exception as e:
            return False, str(e)

    # =========================================================================
    # Törzsadatok — Bankszámlaszám (dbo.Bankszamlaszam_torzs)
    # =========================================================================

    def query_bank_account_numbers(self) -> pd.DataFrame:
        """Bankszámlaszám törzsadatok lekérdezése (ID oszloppal együtt).

        Az ID oszlop a megjelenítésből el van rejtve, de a CRUD műveletekhez szükséges.
        """
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

    def delete_bank_account(self, id: int):
        """Bankszámlaszám sor törlése ID alapján."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM dbo.Bankszamlaszam_torzs WHERE ID=?", (id,)
            )
            conn.commit()
            conn.close()
            return True, "Bankszámlaszám sikeresen törölve."
        except Exception as e:
            return False, str(e)

    def insert_bank_account(
        self,
        bankszamlaszam: str,
        fokonyv: str,
        deviza: str,
        tipus: str,
        partner: str,
    ):
        """Új bankszámlaszám sor INSERT-je.

        Az ID oszlop auto-increment — nem szerepel az INSERT-ben.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO dbo.Bankszamlaszam_torzs "
                "(Bankszamlaszam, Bankszamlaszam_fokonyv, Bankszamlaszam_deviza, "
                "Bankszamlaszam_tipus, Partner) "
                "VALUES (?, ?, ?, ?, ?)",
                (bankszamlaszam, fokonyv, deviza, tipus, partner),
            )
            conn.commit()
            conn.close()
            return True, "Bankszámlaszám sikeresen hozzáadva."
        except Exception as e:
            return False, str(e)

    def update_bank_account(
        self,
        id: int,
        bankszamlaszam: str,
        fokonyv: str,
        deviza: str,
        tipus: str,
        partner: str,
    ):
        """Meglévő bankszámlaszám sor UPDATE-je ID alapján."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE dbo.Bankszamlaszam_torzs "
                "SET Bankszamlaszam=?, Bankszamlaszam_fokonyv=?, "
                "Bankszamlaszam_deviza=?, Bankszamlaszam_tipus=?, Partner=? "
                "WHERE ID=?",
                (bankszamlaszam, fokonyv, deviza, tipus, partner, id),
            )
            conn.commit()
            conn.close()
            return True, "Bankszámlaszám adatai sikeresen frissítve."
        except Exception as e:
            return False, str(e)

    def insert_bank_account_number_rows_bulk(self, df):
        """Bankszámlaszámok tömeges INSERT-je (bulk, az ID nélkül).

        Jelenleg nem aktívan használt metódus — jövőbeli importáláshoz fenntartva.
        A tábla ID oszlopa auto-increment, ezért nem szerepel az INSERT-ben.
        """
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

                # ID oszlop kihagyva (auto-increment)
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

    # =========================================================================
    # Törzsadatok — Bank belső kód (dbo.Bank_belsokod)
    # =========================================================================

    def query_bank_internal_codes(self) -> pd.DataFrame:
        """Bank belső kód törzsadatok lekérdezése (ID oszloppal)."""
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

    def delete_bank_internal_code(self, id: int):
        """Bank belső kód sor törlése ID alapján."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dbo.Bank_belsokod WHERE ID=?", (id,))
            conn.commit()
            conn.close()
            return True, "Belső kód sikeresen törölve."
        except Exception as e:
            return False, str(e)

    def insert_bank_internal_code(self, belsokod: str, fokony: str, fokonyvtext: str):
        """Új belső kód sor INSERT-je."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO dbo.Bank_belsokod (Belsokod, Fokony, FokonyvText) "
                "VALUES (?, ?, ?)",
                (belsokod, fokony, fokonyvtext),
            )
            conn.commit()
            conn.close()
            return True, "Belső kód sikeresen hozzáadva."
        except Exception as e:
            return False, str(e)

    def update_bank_internal_code(
        self, id: int, belsokod: str, fokony: str, fokonyvtext: str
    ):
        """Meglévő belső kód sor UPDATE-je ID alapján."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE dbo.Bank_belsokod "
                "SET Belsokod=?, Fokony=?, FokonyvText=? "
                "WHERE ID=?",
                (belsokod, fokony, fokonyvtext, id),
            )
            conn.commit()
            conn.close()
            return True, "Belső kód adatai sikeresen frissítve."
        except Exception as e:
            return False, str(e)

    def insert_bank_internal_code_rows_bulk(self, df):
        """Bank belső kódok tömeges INSERT-je (bulk, jelenleg nem aktívan használt)."""
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

                # ID oszlop kihagyva (auto-increment)
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

    # =========================================================================
    # Törzsadatok — Partner mapping (dbo.Partner_mapping)
    # =========================================================================

    def query_partner_mapping(self) -> pd.DataFrame:
        """Partner mapping törzsadatok lekérdezése (ID oszloppal).

        Megjegyzés: az adatbázisban az oszlop neve "UMS_parnter" (typo!),
        ezt a nézetek _COL_MAP segítségével "UMS partner"-re fordítják.
        """
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

    def delete_partner(self, id: int):
        """Partner sor törlése ID alapján."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM dbo.Partner_mapping WHERE ID=?", (id,))
            conn.commit()
            conn.close()
            return True, "Partner sikeresen törölve."
        except Exception as e:
            return False, str(e)

    def insert_partner(self, ums_partner: str, combosoft_partner: str):
        """Új partner sor INSERT-je.

        Megjegyzés: az oszlopnév "UMS_parnter" (typo az adatbázisban).
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO dbo.Partner_mapping (UMS_parnter, Combosoft_partner) "
                "VALUES (?, ?)",
                (ums_partner, combosoft_partner),
            )
            conn.commit()
            conn.close()
            return True, "Partner sikeresen hozzáadva."
        except Exception as e:
            return False, str(e)

    def update_partner(self, id: int, ums_partner: str, combosoft_partner: str):
        """Meglévő partner sor UPDATE-je ID alapján."""
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE dbo.Partner_mapping "
                "SET UMS_parnter=?, Combosoft_partner=? "
                "WHERE ID=?",
                (ums_partner, combosoft_partner, id),
            )
            conn.commit()
            conn.close()
            return True, "Partner adatai sikeresen frissítve."
        except Exception as e:
            return False, str(e)

    def call_partner_insert(self):
        """UMS partnerek szinkronizálása: dbo.partnerInsert tárolt eljárás hívása.

        Az eljárás a Bank_lek1 nézetből (importált banki adatok) beolvassa
        az ismeretlen partnerneveket és beilleszti a Partner_mapping táblába.
        Csak az még nem szereplő neveket adja hozzá.
        """
        try:
            conn = self.raw_connect()
            cursor = conn.cursor()
            cursor.execute("{CALL dbo.partnerInsert}")
            conn.commit()
            conn.close()
            return True, "Az UMS partner szinkronizálás sikeresen lefutott."
        except Exception as e:
            return False, str(e)
