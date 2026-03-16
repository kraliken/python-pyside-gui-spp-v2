import os
import re
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import Qt
from models.pandas_model import PandasModel
from ui.dialogs.file_import_progress import ProgressDialog
from ui.views.base_import_view import BaseImportView


class CustomerExcelImportView(BaseImportView):
    def __init__(self):
        """UI nézet vevő (customer) Excel (.xlsx) importhoz és validált DB-mentéshez."""
        super().__init__()
        self.setup_ui(
            "Vevő adatok importálása", import_button_label="Fájl kiválasztása"
        )

        self.df_to_save_in_db = pd.DataFrame()
        self.current_file = None

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
            "Invoice Number",
            "Pro-Forma Invoice",
            "Tax Document",
            "Final Invoice",
            "Corrected Invoice",
            "Counter Party",
            "Counter Party Unique ID",
            "Recipient VAT Number",
            "Recipient Group VAT Number",
            "Lease Group ID",
            "Settlement/Reference",
            "VAT Settlement",
            "Status",
            "Description",
            "Remarks Available in the Bulk Invoice Editor",
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
            "Transaction ID.1",
            "Paym Date",
            "Paym Settlement",
            "Payment Line Bank Statement Reference",
            "Internal Remarks",
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
        """Egyetlen .xlsx fájl betöltése, fejlécellenőrzés, majd transzformáció megjelenítéshez/mentéshez."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Válassz egy .XLSX fájlt", "", "XLSX fájlok (*.xlsx)"
        )

        if not path:
            return

        abs_path = os.path.abspath(path)
        filename = os.path.basename(path)

        if self.current_file and abs_path == self.current_file:
            QMessageBox.information(
                self, "Már betöltve", "Ez a fájl már be van töltve."
            )
            return

        if not path.lower().endswith(".xlsx"):
            QMessageBox.warning(self, "Hiba", "Csak .xlsx fájl importálható.")
            return

        if self.current_file:
            self.clear_data()

        self.progress_dialog = ProgressDialog()
        self.progress_dialog.show()
        QApplication.processEvents()

        filename = os.path.basename(path)

        try:
            df = pd.read_excel(abs_path, header=1, dtype=str)
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

            actual_cols = df.columns.tolist()
            expected_cols = self.expected_columns

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

            self.file_list_widget.addItem(filename)
            self.current_file = abs_path

            self.df_to_save_in_db["bankszamlaszam"] = df["Paym Settlement"].fillna("")
            self.df_to_save_in_db["datum"] = df["Paym Date"].fillna("")
            self.df_to_save_in_db["fajl"] = ""
            self.df_to_save_in_db["fizetesi ID"] = df["Transaction ID.1"].fillna("")
            self.df_to_save_in_db["típus"] = "vevő"
            self.df_to_save_in_db["deviza"] = df["Paym Currency"].fillna("")
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

            self.df_to_save_in_db["partner neve"] = (
                df["Counter Party"]
                .fillna("")
                .mask(
                    df["Invoice Number"].fillna("").str.strip().eq("")
                    & df["Transaction Type"].eq("UNALLOCATED_PAYMENT")
                    & df["Counter Party"].fillna("").str.strip().eq(""),
                    "UNALLOCATED_PARTNER",
                )
            )

            self.df_to_save_in_db["szamlaszam"] = (
                df["Invoice Number"]
                .fillna("")
                .mask(
                    df["Invoice Number"].isna()
                    & (df["Transaction Type"] == "UNALLOCATED_PAYMENT"),
                    "UNALLOCATED_PAYMENT",
                )
            )

            self.df_to_save_in_db["bankszamlaszam"] = (
                self.df_to_save_in_db["bankszamlaszam"]
                .astype(str)
                .apply(lambda x: x.strip())
                .apply(
                    lambda x: (
                        re.search(r"HU\d{2}\s*([\d\s]{14,})", x)
                        .group(1)
                        .replace(" ", "")[:16]
                        if re.search(r"HU\d{2}\s*([\d\s]{14,})", x)
                        else (
                            "".join(re.search(r":\s*(\d{8})-(\d{8})", x).groups())
                            if re.search(r":\s*(\d{8})-(\d{8})", x)
                            else ""
                        )
                    )
                )
                .apply(lambda num: f"{num[:8]}-{num[8:]}" if len(num) == 16 else num)
            )

            self.df_to_save_in_db["datum"] = pd.to_datetime(
                self.df_to_save_in_db["datum"], errors="coerce"
            ).dt.strftime("%Y.%m.%d")

            self.df_to_save_in_db["osszeg"] = pd.to_numeric(
                self.df_to_save_in_db["osszeg"], errors="coerce"
            )

            self.clear_button.setEnabled(True)
            self.save_button.setEnabled(True)

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
            if self.progress_dialog:
                self.progress_dialog.accept()
                self.progress_dialog = None

    def get_data_for_save(self) -> pd.DataFrame:
        return self.df_to_save_in_db.copy()

    def validate_for_insert(self, df: pd.DataFrame) -> bool:
        """Ellenőrzi a mentéshez szükséges mezőket és jelöli a hibás sorokat."""
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

        invalid_type = df[df["típus"] != "vevő"]
        if not invalid_type.empty:
            errors.append("A 'típus' mező minden sorban 'vevő' kell legyen.")
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
            QMessageBox.warning(
                self,
                "Validációs hiba",
                "A következő hibák miatt nem lehet menteni:\n\n" + "\n".join(errors),
            )
            return False

        return True

    def run_database_save(self, df: pd.DataFrame) -> None:
        """DB bulk insert futtatása (UI threadből időzítve hívva)."""
        df = df.copy()
        df.columns = [f"Column{i}" for i in range(1, 10)]
        success, message = self.db.insert_customer_rows_bulk(df)
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
        self.current_file = None
        self.df_to_save_in_db = pd.DataFrame()
