import os
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import Qt
from datetime import datetime
from ui.dialogs.file_import_progress import ProgressDialog
from ui.views.base_import_view import BaseImportView


class BankImportView(BaseImportView):
    def __init__(self):
        super().__init__()
        self.setup_ui(
            "Banki adatok importálása", import_button_label="Fájlok kiválasztása"
        )

        self.df_all = pd.DataFrame()
        self.loaded_files = set()

    # -------------------------------------------------------------------------
    # BaseImportView kötelező implementációk
    # -------------------------------------------------------------------------

    def load_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Válassz .UMS fájlokat", "", "UMS fájlok (*.ums)"
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
            self.loaded_files.add(file)
            self.file_list_widget.addItem(filename)

            try:
                df = pd.read_csv(
                    file,
                    sep=";",
                    header=None,
                    encoding="windows-1250",
                    dtype=str,
                )
                while df.shape[1] < 38:
                    df[df.shape[1]] = ""
                df.columns = [f"Column{i+1}" for i in range(38)]
                all_new_data.append(df)

            except Exception as e:
                QMessageBox.warning(
                    self, "Hiba", f"{filename} beolvasása sikertelen:\n{str(e)}"
                )

        if not all_new_data:
            QMessageBox.information(
                self, "Nincs adat", "Nem található beolvasható .UMS fájl."
            )
            return

        new_df = pd.concat(all_new_data, ignore_index=True)

        for col in ["Column4", "Column14"]:
            if col in new_df.columns:
                new_df[col] = new_df[col].apply(self.fix_short_date)

        if "Column30" in new_df.columns and "Column31" in new_df.columns:
            combined = (
                new_df["Column30"].fillna("") + "" + new_df["Column31"].fillna("")
            )
            mask = combined.str.contains("BUDAPEST 15 PP", case=False, na=False)
            new_df.loc[mask, "Column30"] = "BUDAPEST 15 PP"

        if "Column30" in new_df.columns and "Column31" in new_df.columns:
            combined = (
                new_df["Column30"].fillna("") + "" + new_df["Column31"].fillna("")
            )
            mask = combined.str.contains("MAGYAR POSTA 1870", case=False, na=False)
            new_df.loc[mask, "Column30"] = "MAGYAR POSTA 1870"
            new_df.loc[mask, "Column31"] = ""

        if "Column30" in new_df.columns and "Column31" in new_df.columns:
            combined = (
                new_df["Column30"].fillna("") + "" + new_df["Column31"].fillna("")
            )
            mask = combined.str.contains("FURGEFUTAR.HU", case=False, na=False)
            new_df.loc[mask, "Column30"] = "FURGEFUTAR.HU"
            new_df.loc[mask, "Column31"] = ""

        self.df_all = pd.concat([self.df_all, new_df], ignore_index=True)

        self.clear_button.setEnabled(True)
        self.save_button.setEnabled(True)

        def format_thousands(val):
            try:
                number = float(str(val).replace(",", "."))
                return f"{number:,.2f}".replace(",", " ").replace(".", ",")
            except ValueError:
                return val

        self.update_table_view(
            self.df_all.fillna(""),
            formatters={"Column11": format_thousands},
            alignments={"Column11": Qt.AlignRight | Qt.AlignVCenter},
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
        return self.df_all

    def validate_for_insert(self, df):
        if df.empty:
            QMessageBox.warning(self, "Hiba", "Nincs adat a mentéshez.")
            return False

        if df.shape[1] < 38:
            QMessageBox.warning(
                self, "Hiba", "Az adatok kevesebb mint 38 oszlopot tartalmaznak."
            )
            return False

        for col_name in df.columns:
            if not df[col_name].dropna().map(lambda x: isinstance(x, str)).all():
                QMessageBox.warning(
                    self,
                    "Hiba",
                    f"A(z) {col_name} oszlopban nem minden érték szöveg (str) típusú.",
                )
                return False

        required_fields = {
            "Column1": "üres",
            "Column2": "üres",
            "Column3": "üres",
            "Column4": "dátum (yyyy.mm.dd)",
            "Column11": "decimális szám",
            "Column14": "dátum (yyyy.mm.dd)",
        }

        for col_name, check_type in required_fields.items():
            if col_name not in df.columns:
                QMessageBox.warning(self, "Hiba", f"Hiányzó oszlop: {col_name}")
                return False

            series = df[col_name]

            if series.isnull().any() or (series.str.strip() == "").any():
                QMessageBox.warning(
                    self, "Hiba", f"A(z) {col_name} mező nem lehet üres."
                )
                return False

            if check_type == "dátum (yyyy.mm.dd)":
                try:
                    pd.to_datetime(series, format="%Y.%m.%d", errors="raise")
                except Exception:
                    QMessageBox.warning(
                        self,
                        "Hiba",
                        f"A(z) {col_name} oszlop nem érvényes dátumformátum: yyyy.mm.dd.",
                    )
                    return False

            elif check_type == "decimális szám":
                try:
                    series.str.replace(",", ".").astype(float)
                except Exception:
                    QMessageBox.warning(
                        self,
                        "Hiba",
                        f"A(z) {col_name} mező nem érvényes decimális szám.",
                    )
                    return False

        return True

    def run_database_save(self, df):
        success, message = self.db.insert_bank_rows_bulk(df)
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
        super().clear_data()
        self.loaded_files.clear()
        self.df_all = pd.DataFrame()

    # -------------------------------------------------------------------------
    # Banki segédmetódusok
    # -------------------------------------------------------------------------

    @staticmethod
    def fix_short_date(date_str):
        try:
            cleaned = str(date_str).strip()
            from datetime import datetime

            parsed = datetime.strptime(cleaned, "%d.%m.%y")
            return parsed.strftime("%Y.%m.%d")
        except (ValueError, TypeError):
            return str(date_str)

    def export_to_excel(self):
        if self.df_all.empty:
            QMessageBox.warning(self, "Hiba", "Nincs adat az exportáláshoz.")
            return

        df_to_export = self.df_all.copy()

        if "Column1" in df_to_export.columns and "Column2" in df_to_export.columns:
            df_to_export["Column1_2"] = (
                df_to_export["Column1"].fillna("")
                + "-"
                + df_to_export["Column2"].fillna("")
            )

        if "Column30" in df_to_export.columns and "Column31" in df_to_export.columns:
            df_to_export["Column30_31"] = (
                df_to_export["Column30"].fillna("")
                + ""
                + df_to_export["Column31"].fillna("")
            )

        export_columns = [
            "Column1_2",
            "Column3",
            "Column4",
            "Column6",
            "Column7",
            "Column11",
            "Column14",
            "Column17",
            "Column18",
            "Column19",
            "Column20",
            "Column21",
            "Column25",
            "Column30_31",
            "Column32",
            "Column33",
        ]

        df_to_export = df_to_export[
            [col for col in export_columns if col in df_to_export.columns]
        ]

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        default_filename = f"bank_export_{timestamp}.xlsx"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Mentés Excel fájlba", default_filename, "Excel fájlok (*.xlsx)"
        )

        if not file_path:
            return

        if not file_path.endswith(".xlsx"):
            file_path += ".xlsx"

        try:
            df_to_export.to_excel(file_path, index=False)
            QMessageBox.information(
                self, "Siker", f"A fájl sikeresen elmentve:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Hiba", f"Hiba történt az exportálás során:\n{str(e)}"
            )
