# ui/views/customer/import_view.py
#
# CustomerImportView — Vevői .XLS fájlok importálása.
#
# A VendorImportView-hoz nagyon hasonló szerkezet, de a vevői exportok
# oszlopai és az adatok kinyerési logikája eltérő.
#
# Fő különbségek a szállítóhoz képest:
#   - expected_columns: különböző fejlécoszlopok (pl. "Payment Date, ID" vs "Status, Payment Date, ID")
#   - extract_iban: a szállítói IBAN-nal ellentétben nem szűr 'Beneficiary' pozícióra
#   - extract_partner_name: "Payer:" prefix után keres (a vevő fizet, nem a partner)
#   - fájl mező: "87" értékkel töltve (hardcoded azonosító)
#
# Folyamat:
#   1. Fájlok kiválasztása (.xls) → HTML beolvasás pd.read_html()-lel
#   2. Fejlécellenőrzés (első 2 oszlop eldobva)
#   3. NaN szűrés (Payment Amounts alapján)
#   4. Kiegészítő oszlopok: IBAN, dátum, ID, deviza/összeg/számlaszám (expand)
#   5. Mentés az IremsVevo_stage táblába

import os
import re
import pandas as pd
from io import StringIO
from itertools import zip_longest
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import Qt
from models.pandas_model import PandasModel
from ui.dialogs.file_import_progress import ProgressDialog
from ui.views.base_import_view import BaseImportView


class CustomerImportView(BaseImportView):
    """Vevői .XLS fájlok importálási nézete.

    Több fájl egyszerre betölthető (akkumuláló mód).
    A .xls fájlok HTML táblázatot tartalmaznak — pd.read_html() olvassa be.
    """

    def __init__(self):
        super().__init__()
        self.setup_ui("Vevő adatok importálása")

        self.df_all = pd.DataFrame()   # összes betöltött fájl összesített adatai
        self.loaded_files = set()       # duplikáció szűréshez

        # Elvárt fejlécek az első 2 oszlop elhagyása után
        # A vevői XLS fejléc eltér a szállítóitól: "Payment Date, ID" vs "Status, Payment Date, ID"
        self.expected_columns = [
            "Information",
            "Payment Date, ID",
            "Payment Amounts",
            "Allocated Invoice Number",
            "Allocated Amount",
            "in Invoice Currency",
            "%",
            "Unpaid (in Inv. Crcy)",
        ]

    # -------------------------------------------------------------------------
    # BaseImportView kötelező implementációk
    # -------------------------------------------------------------------------

    def load_files(self):
        """Fájlválasztó dialógus, XLS fájlok beolvasása HTML-ként.

        Azonos megközelítés a VendorImportView-val: a .xls fájl belseje
        HTML táblázat (Irems/SAP export). Az első 2 oszlop eldobódik.
        """
        files, _ = QFileDialog.getOpenFileNames(
            self, "Válassz .XLS fájlokat", "", "XLS fájlok (*.xls)"
        )

        if not files:
            return

        duplicates = [f for f in files if f in self.loaded_files]
        new_files = [f for f in files if f not in self.loaded_files]

        if not new_files:
            if duplicates:
                QMessageBox.warning(
                    self,
                    "Ismétlődő fájlok",
                    f"A következő fájl(ok) már be lettek olvasva:\n"
                    + "\n".join(os.path.basename(f) for f in duplicates),
                )
            return

        all_new_data = []
        self.loaded_files.update(new_files)

        self.progress_dialog = ProgressDialog()
        self.progress_dialog.show()
        QApplication.processEvents()

        for file in new_files:
            filename = os.path.basename(file)

            try:
                # HTML tartalom beolvasása windows-1252 kódolással
                with open(file, "r", encoding="windows-1252", errors="replace") as f:
                    html = f.read()

                df_list = pd.read_html(StringIO(html), header=0)

                if not df_list:
                    raise ValueError("Nem találtunk HTML táblázatot.")

                # Első táblázat, első 2 oszlop eldobva
                df = df_list[0].iloc[:, 2:]

                # Fejléc egyezés ellenőrzés
                if df.columns.tolist() != self.expected_columns:
                    if self.progress_dialog:
                        self.progress_dialog.accept()
                        self.progress_dialog = None
                    QMessageBox.warning(
                        self,
                        "Fejléc eltérés",
                        f"A(z) '{filename}' fájl fejlécszerkezete eltér az elvárttól, ezért kihagytuk.",
                    )
                    continue

                self.loaded_files.add(file)
                self.file_list_widget.addItem(filename)
                all_new_data.append(df)

            except Exception as e:
                if self.progress_dialog:
                    self.progress_dialog.accept()
                    self.progress_dialog = None
                QMessageBox.warning(
                    self, "Hiba", f"{filename} beolvasása sikertelen:\n{str(e)}"
                )

        if not all_new_data:
            QMessageBox.information(
                self, "Nincs adat", "Nem található beolvasható .XLS fájl."
            )
            return

        new_df = pd.concat(all_new_data, ignore_index=True)

        # NaN szűrés: Payment Amounts üres sorok kiesnek
        new_df = new_df.dropna(subset=["Payment Amounts"])

        # Kiegészítő oszlopok kiszámítása
        # A vevői XLS Information mezőjéből kinyerjük az IBAN-t
        new_df["Számlaszám (HU)"] = new_df["Information"].apply(self.extract_iban)
        new_df["Számlaszám (formázott)"] = new_df["Számlaszám (HU)"].apply(
            self.format_hungarian_account_number
        )
        # A vevői dátum a "Payment Date, ID" mezőben van (szállítóinál "Status, Payment Date, ID")
        new_df["Fizetési dátum"] = new_df["Payment Date, ID"].apply(
            self.extract_payment_date
        )
        new_df["fájl"] = "87"  # hardcoded fájlazonosító (vevői adat forrása: "87")
        new_df["Fizetési ID"] = new_df["Payment Date, ID"].apply(
            self.extract_payment_id
        )
        new_df["típus"] = "VEVŐ"

        # expand_amount_paid(): egy sorból több sor, ha több összeg/deviza/számla van
        # A vevői Allocated Amount és Allocated Invoice Number mezőkből dolgozik
        new_df = self.expand_amount_paid(new_df)

        # Partner neve (a vevői oldalon a "Payer:" mező tartalmazza)
        new_df["Partner neve"] = new_df["Information"].apply(self.extract_partner_name)

        # Oszlopsorrend csere: Számlaszám és Partner neve helyet cserél
        cols = new_df.columns.tolist()
        idx_szamlaszam = cols.index("Számlaszám")
        idx_partner = cols.index("Partner neve")
        cols[idx_szamlaszam], cols[idx_partner] = cols[idx_partner], cols[idx_szamlaszam]
        new_df = new_df[cols]

        # Hozzáfűzés a meglévő adatokhoz (akkumuláló mód)
        self.df_all = pd.concat([self.df_all, new_df], ignore_index=True)

        self._on_file_loaded()

        def format_thousands(val):
            try:
                number = float(str(val).replace(",", "."))
                return f"{number:,.2f}".replace(",", " ").replace(".", ",")
            except ValueError:
                return val

        self.update_table_view(
            self.df_all,
            formatters={"Összeg": format_thousands},
            alignments={"Összeg": Qt.AlignRight | Qt.AlignVCenter},
        )

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if duplicates:
            QMessageBox.warning(
                self,
                "Ismétlődő fájlok",
                f"A következő fájl(ok) már be lettek olvasva:\n"
                + "\n".join(os.path.basename(f) for f in duplicates),
            )

    def get_data_for_save(self) -> pd.DataFrame:
        """Az utolsó 9 feldolgozott oszlopot adja vissza — ezek kerülnek az IremsVevo_stage-be."""
        return self.df_all.iloc[:, -9:].copy()

    def validate_for_insert(self, df):
        """Ellenőrzi az adatok érvényességét DB-mentés előtt.

        Ellenőrzések megegyeznek a VendorImportView-val, kivéve:
          - fájl mező is kötelező (CustomerImportView-ban "87" a hardcoded érték)
          - típus: 'VEVŐ' (nagybetűs, a szállítónál kisbetűs)
        """
        required_columns = [
            "Számlaszám (formázott)",
            "Fizetési dátum",
            "fájl",
            "Fizetési ID",
            "típus",
            "Deviza",
            "Összeg",
            "Partner neve",
            "Számlaszám",
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
            pd.to_datetime(df["Fizetési dátum"], format="%Y.%m.%d", errors="raise")
        except Exception:
            errors.append(
                "A 'Fizetési dátum' mező nem megfelelő formátumú vagy hibás dátumot tartalmaz (pl. 2024.02.30)."
            )
            error_rows.update(df.index)

        try:
            df["Összeg"].astype(str).str.replace(",", ".").astype(float)
        except Exception:
            errors.append("Az 'Összeg' mező nem konvertálható decimális számmá.")
            error_rows.update(df.index)

        # típus ellenőrzés — vevőknél nagybetűs 'VEVŐ'
        invalid_type = df[df["típus"] != "VEVŐ"]
        if not invalid_type.empty:
            errors.append("A 'típus' mező minden sorban 'VEVŐ' kell legyen.")
            error_rows.update(invalid_type.index)

        invalid_currencies = df[~df["Deviza"].isin(allowed_currencies)]
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
        """Elvégzi a tömeges adatbázis-mentést az IremsVevo_stage táblába."""
        df = df.copy()
        df.columns = [f"Column{i}" for i in range(1, 10)]  # Column1..Column9 átnevezés
        success, message = self.db.insert_customer_rows_bulk(df)
        self.hide_progress()

        if success:
            self.clear_data()
            QMessageBox.information(self, "Siker", message)
        else:
            QMessageBox.critical(self, "Hiba", message)

    # -------------------------------------------------------------------------
    # clear_data override
    # -------------------------------------------------------------------------

    def clear_data(self):
        """Az alap törlés mellett törli a betöltött fájlok halmazát és a DataFrame-et."""
        super().clear_data()
        self.loaded_files.clear()
        self.df_all = pd.DataFrame()

    # -------------------------------------------------------------------------
    # Vevői segédmetódusok
    # -------------------------------------------------------------------------

    def extract_iban(self, cell_text):
        """IBAN bankszámlaszám kinyerése az Information mezőből.

        A vevői változat nem szűr 'Beneficiary' pozícióra (ellentétben a szállítóival),
        mert a vevők esetén az IBAN más kontextusban szerepel.
        A regex az első HU-val kezdődő IBAN-t keresi.
        """
        pattern = r"(HU\d{2}(?:\s?\d{4}){6})"
        match = re.search(pattern, str(cell_text))
        return match.group(1) if match else ""

    def format_hungarian_account_number(self, iban):
        """IBAN → rövid magyar bankszámlaszám: DDDDDDDD-DDDDDDDD."""
        match = re.search(r"HU\d{2}(\d{8})\s?(\d{8})", iban.replace(" ", ""))
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return ""

    def extract_payment_date(self, cell_text):
        """Fizetési dátum kinyerése a Payment Date, ID mezőből.

        A vevői mező formátuma: "2024.03.15 ID: 123456"
        (nincs állapotszó előtte, ellentétben a szállítói "Executed 2024.03.15" formátummal).
        """
        match = re.search(r"(\d{4}\.\d{2}\.\d{2})", str(cell_text))
        return match.group(1) if match else ""

    def extract_payment_id(self, cell_text: str) -> str:
        """Fizetési azonosító (ID) kinyerése a Payment Date, ID mezőből."""
        match = re.search(r"ID:\s*(\d+)", str(cell_text))
        return match.group(1) if match else ""

    def extract_partner_name(self, text: str) -> str:
        """Partner (vevő) nevének kinyerése az Information mezőből.

        A vevői oldalon a fizető fél neve a 'Payer:' prefix után szerepel.
        Formátum: "... Payer: PARTNER NÉV Beneficiary Bank Acct: ..."
        """
        match = re.search(r"Payer:\s*(.*?)\s*Beneficiary Bank Acct:", str(text))
        return match.group(1).strip() if match else ""

    def expand_amount_paid(self, df):
        """Egy sorból több sort képez, ha több összeg/deviza/számlaszám van.

        A vevői Allocated Amount és Allocated Invoice Number mezőkből dolgozik.
        Az "Allocated Invoice Number" mező számlaszámokat tartalmaz (nem "Invoice " prefix-szel,
        ellentétben a szállítói "Invoice ABC/..." formátummal).

        Példa:
          Allocated Amount = "[1000 HUF, 500 EUR]"
          Allocated Invoice Number = "[ABC/2024/00001, DEF/2024/00002]"
          → 2 sor: (1000 HUF, ABC/2024/00001) és (500 EUR, DEF/2024/00002)
        """
        rows = []
        raw_amounts = df["Allocated Amount"].fillna("").astype(str).str.strip("[]")
        raw_lines = df["Allocated Invoice Number"].fillna("").astype(str).str.strip("[]")

        for idx, (raw_amount, raw_line) in enumerate(zip(raw_amounts, raw_lines)):
            # Összeg + deviza párok regex-szel
            amount_matches = re.findall(
                r"(-?[\d\s\u00A0]+(?:,\d{2})?)\s*([A-Z]{3})", raw_amount
            )
            # Vevői számlaszám minta: "ABC/2024/00001" (opcionális prefix/suffix)
            invoice_matches = re.findall(
                r"(?:[A-Z]+/)?\d{4}/\d{5}(?:/[A-Z]+)?", raw_line
            )

            for (amount_raw, currency), invoice in zip_longest(
                amount_matches, invoice_matches, fillvalue=""
            ):
                amount = amount_raw.replace(" ", "").replace("\u00a0", "")
                row = df.iloc[idx]
                rows.append(
                    {
                        **row.to_dict(),
                        "Deviza": currency,
                        "Összeg": amount,
                        "Számlaszám": invoice,
                    }
                )

        return pd.DataFrame(rows)
