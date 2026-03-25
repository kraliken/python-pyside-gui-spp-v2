# ui/views/vendor/excel_import_view.py
#
# VendorExcelImportView — Szállítói .XLSX fájlok importálása (Combosoft/Irems export).
#
# A VendorImportView (.xls, HTML alapú) mellé kiegészítő importálási nézet,
# amely az újabb Irems XLSX formátumot kezeli (69 oszlop).
#
# Folyamat:
#   1. Egyetlen .xlsx fájl kiválasztása → pd.read_excel (fejléc a 2. sorban, header=1)
#   2. "Unnamed" fejlécű oszlopok eldobása
#   3. Fejléc egyezés ellenőrzése: oszlopszám és oszlopnév pozíció szerint
#   4. Adattranszformáció: 9 céloszlop kiszámítása a forrásmezőkből:
#      - bankszamlaszam: Paym Settlement → regex alapú IBAN/DEP/HU: normalizálás
#      - datum: Paym Date → pandas datetime → YYYY.MM.DD
#      - fizetesi ID: Transaction ID.1 (ha üres, akkor a Transaction ID 2. előfordulása)
#      - osszeg: Allocated Amount in Payment Currency (ha üres: Unallocated in Payment Currency)
#      - deviza, partner neve, szamlaszam
#   5. Mentés az IremsSzallito_stage táblába (bulk insert)
#
# _get_column(): statikus segédmetódus duplikált fejlécű oszlopok kezeléséhez
# (az XLSX-ben a "Transaction ID" kétszer szerepelhet, különböző adatokkal).

import os
import re                # reguláris kifejezések (bankszámlaszám normalizáláshoz)
import pandas as pd      # Excel beolvasás és adatkezelés
from typing import Sequence, Tuple  # típusjelölések a _get_column metódus paramétereihez
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from models.pandas_model import PandasModel                # DataFrame → QTableView
from PySide6.QtCore import Qt
from ui.dialogs.file_import_progress import ProgressDialog # fájlbeolvasási várakozó dialógus
from ui.views.base_import_view import BaseImportView       # közös import nézet logika


class VendorExcelImportView(BaseImportView):
    """Szállítói .XLSX fájlok importálási nézete (egyszerre 1 fájl).

    Ellentétben a VendorImportView-val (több fájl, akkumuláló), ez a nézet
    egyszerre csak 1 fájlt tölt be — ha újat választ a felhasználó, az előző törlődik.
    """

    def __init__(self):
        super().__init__()  # BaseImportView inicializálása
        self.setup_ui(
            "Szállító adatok importálása", import_button_label="Fájl kiválasztása"
        )

        # Csak 1 fájlt tárol — ellentétben a VendorImportView df_all megközelítésével
        self.df_to_save_in_db = pd.DataFrame()  # a DB-be mentendő 9 oszlopos DataFrame
        self.current_file = None                # az éppen betöltött fájl abszolút útvonala

        # 69 elvárt oszlopnév az XLSX fejlécében (2. sor, Unnamed oszlopok nélkül)
        # Ha az oszlopszám vagy az oszlopnevek nem egyeznek, a fájl visszautasításra kerül
        self.expected_columns = [
            "Transaction Type",
            "Managed Entity",
            "Managed Entity Unique ID",
            "Partner Type",
            "Legal Issuer",
            "Issuer VAT Number",
            "Issuer Group VAT Number",
            "Legal Invoice Issuer Unique ID",
            "Transaction ID",
            "Country",
            "Approval Date",
            "Invoice Number",
            "Pro-Forma Invoice",
            "Tax Document",
            "Final Invoice",
            "Corrected Invoice",
            "Counter Party",
            "Counter Party Unique ID",
            "Recipient VAT Number",
            "Recipient Group VAT Number",
            "Settlement/Reference",
            "Status",
            "Description",
            "Invoice Date",
            "Acct. Delivery Date",
            "VAT Delivery Date",
            "Due Date",
            "Invoice Creation Date",
            "Invoice Last Modified Date",
            "Inv Currency",
            "Invoice Net",
            "Invoice Vat Amount",
            "Invoiced Gross",
            "Invoice Creation Paid",
            "Outstanding",
            "GL FX Rate",
            "FX Rate Type",
            "FX Rate Date",
            "Reporting Currency",
            "Reporting Amount",
            "Historical FX",
            "Invoiced Gross (As of Fx Date)",
            "Invoiced Gross Historical",
            "Outstanding As Of FX Date",
            "Invoice External System IDs",
            "Issuer External System IDs",
            "Recipient External System IDs",
            "Allocated Amount in Invoice Currency",
            "Allocated Amount in G/L Crcy",
            "Allocated Amount in Payment Currency",
            "Payment Total Allocated Amount in Payment Currency",
            "Unallocated in G/L Crcy",
            "Unallocated in Payment Currency",
            "Paid Amount (Paym Crcy)",
            "Paym Currency",
            "Paid Amount in GL Currency",
            "GL Currency",
            "Payment Status",
            "Transaction ID.1",      # duplikált fejléc! (ez a fizetési tranzakció ID-ja)
            "Paym Date",
            "Paym Settlement",
            "Payment Line Bank Statement Reference",
            "Internal Remarks",
            "Paid From",
            "Paid To",
            "Payment Last Modified Date",
            "Last Modifier",
            "Account Number - A/P or A/R",
            "Account Number - Bank Account",
        ]

    # -------------------------------------------------------------------------
    # BaseImportView kötelező implementációk
    # -------------------------------------------------------------------------

    def load_files(self):
        """Egyetlen .xlsx fájl betöltése, fejlécellenőrzés, majd transzformáció.

        Az XLSX fejléc a 2. sorban van (header=1 — nullás indexelés).
        Az 1. sor összesített fejléc szövegeket tartalmaz (Unnamed: X formában).
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Válassz egy .XLSX fájlt", "", "XLSX fájlok (*.xlsx)"
        )

        if not path:
            return  # felhasználó visszalépett

        abs_path = os.path.abspath(path)  # abszolút útvonal (duplikáció ellenőrzéshez)
        filename = os.path.basename(path)

        # Ha ugyanaz a fájl van már betöltve, figyelmeztető üzenet
        if self.current_file and abs_path == self.current_file:
            QMessageBox.information(
                self, "Már betöltve", "Ez a fájl már be van töltve."
            )
            return

        if not path.lower().endswith(".xlsx"):
            QMessageBox.warning(self, "Hiba", "Csak .xlsx fájl importálható.")
            return

        # Ha már van betöltve fájl, töröljük az előző adatokat (egyfájlos mód)
        if self.current_file:
            self.clear_data()

        # Progress dialógus megjelenítése
        self.progress_dialog = ProgressDialog()
        self.progress_dialog.show()
        QApplication.processEvents()

        filename = os.path.basename(path)

        try:
            # XLSX beolvasás — header=1: 2. sor a fejléc, dtype=str: minden értéket string-ként kezel
            df = pd.read_excel(abs_path, header=1, dtype=str)
            # "Unnamed:" prefixű oszlopok eldobása (az 1. sor összesítő fejléceinek maradványai)
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

            actual_cols = df.columns.tolist()
            expected_cols = self.expected_columns

            # Oszlopszám ellenőrzés
            if len(actual_cols) != len(expected_cols):
                if self.progress_dialog:
                    self.progress_dialog.accept()
                    self.progress_dialog = None
                QMessageBox.warning(
                    self,
                    "Fejléc eltérés",
                    (
                        f"A(z) '{filename}' fájl fejlécszerkezete eltér az elvárttól.\n\n"
                        f"Oszlopszám nem egyezik.\n"
                        f"Elvárt: {len(expected_cols)} oszlop, kapott: {len(actual_cols)}."
                    ),
                )
                return

            # Pozíció alapú oszlopnév egyezés ellenőrzés
            mismatches = []
            for idx, (got, exp) in enumerate(zip(actual_cols, expected_cols), start=1):
                if got != exp:
                    mismatches.append((idx, exp, got))

            if mismatches:
                if self.progress_dialog:
                    self.progress_dialog.accept()
                    self.progress_dialog = None
                diff_lines = "\n".join(
                    f"{i}. oszlop – elvárt: {exp} | kapott: {got}"
                    for i, exp, got in mismatches
                )
                QMessageBox.warning(
                    self,
                    "Fejléc eltérés",
                    (
                        f"A(z) '{filename}' fájl fejlécszerkezete eltér az elvárttól.\n\n"
                        f"{len(mismatches)} eltérés található pozíció szerint:\n{diff_lines}"
                    ),
                )
                return

            self.file_list_widget.addItem(filename)   # bal panel fájllistájához hozzáadás
            self.current_file = abs_path              # aktuális fájl rögzítése

            # --- Céloszlopok kiszámítása forrásmezőkből ---

            # Banki elszámolási mező (Paym Settlement) — IBAN/DEP/HU: formátumú szöveg
            paym_settlement = self._get_column(df, "Paym Settlement")
            paym_date = self._get_column(df, "Paym Date")
            paym_currency = self._get_column(df, "Paym Currency")
            counter_party = self._get_column(df, "Counter Party")    # partner neve
            invoice_number = self._get_column(df, "Invoice Number")  # számlaszám

            # Transaction ID.1 az XLSX-ben a fizetési tranzakció ID-ja
            # Ha üres (régebbi exportban "Transaction ID" kétszer szerepel),
            # a Transaction ID 2. előfordulását vesszük (_get_column occurrence=2)
            payment_transaction_id = self._get_column(df, "Transaction ID.1")
            if payment_transaction_id.eq("").all():
                payment_transaction_id = self._get_column(
                    df, "Transaction ID", occurrence=2
                )

            # 9 céloszlop feltöltése
            self.df_to_save_in_db["bankszamlaszam"] = paym_settlement
            self.df_to_save_in_db["datum"] = paym_date
            self.df_to_save_in_db["fajl"] = ""  # üres fájlazonosító
            self.df_to_save_in_db["fizetesi ID"] = payment_transaction_id
            self.df_to_save_in_db["típus"] = "szállító"
            self.df_to_save_in_db["deviza"] = paym_currency

            # Összeg: ha Allocated Amount in Payment Currency üres, akkor
            # az Unallocated in Payment Currency értéket vesszük
            # .where(cond, other): ahol cond False, ott other értéket helyezi be
            self.df_to_save_in_db["osszeg"] = (
                df["Allocated Amount in Payment Currency"]
                .fillna("")
                .astype(str)
                .where(
                    df["Allocated Amount in Payment Currency"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .ne(""),
                    df["Unallocated in Payment Currency"].fillna(""),
                )
            )
            self.df_to_save_in_db["partner neve"] = counter_party
            self.df_to_save_in_db["szamlaszam"] = invoice_number

            # --- Bankszámlaszám normalizálása ---
            # Három lehetséges forrásformátum:
            #   1. IBAN: "HUxx 12345678 90123456" → "12345678-90123456"
            #   2. HU:   "HU: 12345678-90123456"   → "12345678-90123456"
            #   3. DEP:  "DEP HUF: 12345678-90123456 (HUF)" → "12345678-90123456"

            # Regex minták előre fordítva (gyorsabb, ha sok sorra alkalmazzuk)
            p_iban = re.compile(r"HU\d{2}\s*([\d\s]{14,})")
            p_hu_dash = re.compile(r"HU:\s*(\d{8})-(\d{8})")
            p_dep = re.compile(
                r"\bDEP\s+[A-Z]{3}:\s*(\d{8})-(\d{8})(?:\s*\([A-Z]{3}\))?",
                re.IGNORECASE,
            )

            def normalize_bank_account(x: str) -> str:
                """Bankszámlaszám normalizálása: különböző forrásmintákból DDDDDDDD-DDDDDDDD."""
                x = str(x)
                # IBAN minta próba
                m = p_iban.search(x)
                if m:
                    num = m.group(1).replace(" ", "")[:16]
                    return f"{num[:8]}-{num[8:]}" if len(num) == 16 else num
                # HU: minta próba
                m = p_hu_dash.search(x)
                if m:
                    num = "".join(m.groups())
                    return f"{num[:8]}-{num[8:]}"
                # DEP minta próba
                m = p_dep.search(x)
                if m:
                    num = "".join(m.groups())
                    return f"{num[:8]}-{num[8:]}"
                return ""  # egyik minta sem illeszkedett

            self.df_to_save_in_db["bankszamlaszam"] = (
                self.df_to_save_in_db["bankszamlaszam"]
                .astype(str)
                .apply(normalize_bank_account)
            )

            # Dátum normalizálás: bármilyen pandas által felismert formátum → "YYYY.MM.DD"
            # errors="coerce": érvénytelen értéket NaT-ra cseréli (nem dob hibát)
            self.df_to_save_in_db["datum"] = pd.to_datetime(
                self.df_to_save_in_db["datum"], errors="coerce"
            ).dt.strftime("%Y.%m.%d")

            # Összeg konverzió: string → numerikus érték (NaN ha nem konvertálható)
            self.df_to_save_in_db["osszeg"] = pd.to_numeric(
                self.df_to_save_in_db["osszeg"], errors="coerce"
            )

            self._on_file_loaded()  # gombállapotok frissítése (BaseImportView)

            # Magyar számformátum a táblázat megjelenítéséhez
            def format_thousands(val):
                try:
                    number = float(str(val).replace(",", "."))
                    return f"{number:,.2f}".replace(",", " ").replace(".", ",")
                except ValueError:
                    return val

            self.update_table_view(
                self.df_to_save_in_db,
                formatters={"osszeg": format_thousands},
                alignments={"osszeg": Qt.AlignRight | Qt.AlignVCenter},
            )

        except Exception as e:
            QMessageBox.warning(
                self, "Hiba", f"{filename} beolvasása sikertelen:\n{str(e)}"
            )
        finally:
            # Progress dialógus bezárása — hiba esetén is
            if self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None

    def get_data_for_save(self) -> pd.DataFrame:
        """A mentendő DataFrame visszaadása (az összes 9 feldolgozott oszlop)."""
        return self.df_to_save_in_db.copy()

    def validate_for_insert(self, df):
        """Ellenőrzi az adatok érvényességét DB-mentés előtt.

        Ellenőrzések:
          - Kötelező oszlopok megléte és kitöltöttsége
          - Dátum formátuma (yyyy.mm.dd)
          - Összeg konvertálhatósága számmá
          - típus: 'szállító' (kisbetűs)
          - Deviza: csak HUF/EUR/USD/GBP/CHF
        """
        required_columns = [
            "bankszamlaszam",
            "datum",
            "fizetesi ID",
            "típus",
            "deviza",
            "osszeg",
            "partner neve",
            "szamlaszam",
        ]

        allowed_currencies = {"HUF", "EUR", "USD", "GBP", "CHF"}
        errors = []
        error_rows = set()

        for col in required_columns:
            invalid = df[df[col].isnull() | (df[col].astype(str).str.strip() == "")]
            if not invalid.empty:
                errors.append(f"Hiányzó érték a(z) '{col}' oszlopban.")
                error_rows.update(invalid.index)

        try:
            pd.to_datetime(df["datum"], format="%Y.%m.%d", errors="raise")
        except Exception:
            errors.append(
                "A 'Fizetési dátum' mező nem megfelelő formátumú vagy hibás dátumot tartalmaz (pl. 2024.02.30)."
            )
            error_rows.update(df.index)

        try:
            df["osszeg"].astype(str).str.replace(",", ".").astype(float)
        except Exception:
            errors.append("Az 'Összeg' mező nem konvertálható decimális számmá.")

        invalid_type = df[df["típus"] != "szállító"]
        if not invalid_type.empty:
            errors.append("A 'típus' mező minden sorban 'szállító' kell legyen.")
            error_rows.update(invalid_type.index)

        invalid_currencies = df[~df["deviza"].isin(allowed_currencies)]
        if not invalid_currencies.empty:
            errors.append(
                "A 'Deviza' mező csak az alábbi értékeket tartalmazhat: "
                + ", ".join(allowed_currencies)
            )
            error_rows.update(invalid_currencies.index)

        if errors:
            model = self.table_view.model()
            if isinstance(model, PandasModel):
                model.set_invalid_rows(error_rows)
            self._error_rows = error_rows
            QMessageBox.warning(
                self,
                "Validációs hiba",
                "A következő hibák miatt nem lehet menteni:\n\n" + "\n".join(errors),
            )
            return False

        return True

    def run_database_save(self, df):
        """Elvégzi a tömeges adatbázis-mentést az IremsSzallito_stage táblába."""
        df = df.copy()
        df.columns = [f"Column{i}" for i in range(1, 10)]  # Column1..Column9 átnevezés
        success, message = self.db.insert_vendor_rows_bulk(df)
        self.hide_progress()

        if success:
            self.clear_data()
            QMessageBox.information(self, "Siker", message)
        else:
            QMessageBox.critical(self, "Hiba", message)

    # -------------------------------------------------------------------------
    # clear_data override (extra állapot törlése)
    # -------------------------------------------------------------------------

    def clear_data(self):
        """Aktuális fájl és táblázat állapotának ürítése."""
        super().clear_data()
        self.current_file = None             # fájl referencia törlése
        self.df_to_save_in_db = pd.DataFrame()  # üres DataFrame

    # -------------------------------------------------------------------------
    # Segédmetódus duplikált fejlécek kezeléséhez
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_column(
        df: pd.DataFrame,
        name: str,
        *,
        occurrence: int = 1,
        alternatives: Sequence[str] = (),
        default: str = "",
    ) -> pd.Series:
        """Oszlop kiolvasása név alapján, duplikált oszlopnevek és fallback elnevezések támogatásával.

        Args:
            df:           a forrás DataFrame
            name:         keresett oszlopnév
            occurrence:   hányadik előfordulást vegyük (1 = első, 2 = második stb.)
                          Oka: az XLSX-ben a "Transaction ID" kétszer szerepelhet,
                          az első az számla tranzakciója, a második a fizetésé.
            alternatives: fallback nevek, ha 'name' nem található
            default:      alapértelmezett érték, ha egyik sem található

        Returns:
            pd.Series az oszlop értékeivel (vagy default értékekkel teli Series)
        """
        candidates: Tuple[str, ...] = (name, *tuple(alternatives))
        for cand in candidates:
            # Ugyanolyan nevű oszlopok pozícióinak listája
            matches = [col for col in df.columns if col == cand]
            if matches and 1 <= occurrence <= len(matches):
                # Az n-edik előfordulás pozíciója az eredeti DataFrame-ben
                positions = [i for i, col in enumerate(df.columns) if col == cand]
                pos = positions[occurrence - 1]
                return df.iloc[:, pos].fillna(default)
        # Egyik variáns sem található: üres Series visszaadása
        return pd.Series([default] * len(df), index=df.index, dtype="object")
