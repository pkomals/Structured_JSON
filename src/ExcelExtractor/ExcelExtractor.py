import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path

class ExcelExtractor:
    """
    Simple Excel extractor that handles both .xls and .xlsx files
    """
    
    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self.file_extension = Path(excel_path).suffix.lower()
        self.pd_sheets = None
        self._load_workbook()
    
    def _load_workbook(self):
        """Load Excel workbook with appropriate engine"""
        print(f"Loading {self.file_extension} file...")
        
        try:
            if self.file_extension == '.xls':
                # Try xlrd first
                try:
                    self.pd_sheets = pd.read_excel(
                        self.excel_path, 
                        sheet_name=None, 
                        header=None, 
                        engine='xlrd'
                    )
                    print("Successfully loaded using xlrd engine")
                except Exception as e:
                    print(f"xlrd failed: {e}")
                    # Try other engines as fallback
                    try:
                        self.pd_sheets = pd.read_excel(
                            self.excel_path, 
                            sheet_name=None, 
                            header=None
                        )
                        print("Successfully loaded using default engine")
                    except Exception as e2:
                        raise Exception(f"All engines failed. xlrd error: {e}, default error: {e2}")
            else:
                # .xlsx files
                try:
                    self.pd_sheets = pd.read_excel(
                        self.excel_path, 
                        sheet_name=None, 
                        header=None, 
                        engine='openpyxl'
                    )
                    print("Successfully loaded using openpyxl engine")
                except Exception as e:
                    print(f"openpyxl failed: {e}")
                    # Try default engine
                    self.pd_sheets = pd.read_excel(
                        self.excel_path, 
                        sheet_name=None, 
                        header=None
                    )
                    print("Successfully loaded using default engine")
                    
        except Exception as e:
            raise Exception(f"Failed to load Excel file: {e}")
    
    def extract_text_pages(self, max_sheets: int = 3) -> List[Dict[str, Any]]:
        """Convert Excel sheets to text pages"""
        text_pages = []
        
        sheet_names = list(self.pd_sheets.keys())[:max_sheets]
        
        for sheet_name in sheet_names:
            sheet_text = self._sheet_to_text(sheet_name)
            text_pages.append({
                "text": sheet_text,
                "sheet_name": sheet_name
            })
        
        return text_pages
    
    def _sheet_to_text(self, sheet_name: str) -> str:
        """Convert sheet to text format"""
        if sheet_name not in self.pd_sheets:
            return ""
        
        df = self.pd_sheets[sheet_name]
        text_lines = []
        
        for index, row in df.iterrows():
            row_text = []
            for value in row:
                if pd.notna(value) and str(value).strip():
                    row_text.append(str(value).strip())
            
            if row_text:
                line = " ".join(row_text)
                if line.strip():
                    text_lines.append(line)
        
        return "\n".join(text_lines)
    
    def extract_tables(self) -> List[Dict[str, Any]]:
        """Convert Excel sheets to table format"""
        tables = []
        
        for sheet_name, df in self.pd_sheets.items():
            table = self._dataframe_to_table(df, sheet_name)
            if table:
                tables.append(table)
        
        return tables
    
    def _dataframe_to_table(self, df: pd.DataFrame, sheet_name: str) -> Dict[str, Any]:
        """Convert DataFrame to table format expected by HeaderBasedTableParser"""
        # Show ALL raw DataFrame content
        # print(f"\nComplete Raw DataFrame content:")
        # for i in range(len(df)):
        #     row_data = list(df.iloc[i])
        #     print(f"  DF Row {i:2d}: {row_data}")

        rows = []
        
        for index, row in df.iterrows():
            row_list = []
            for value in row:
                if pd.isna(value):
                    row_list.append(None)
                else:
                    row_list.append(str(value).strip())
            
            # NEW: Remove leading None columns if they're consistently empty
            while row_list and row_list[0] is None:
                row_list.pop(0)
            
            if any(cell and str(cell).strip() for cell in row_list):
                rows.append(row_list)
        
        # BETTER FIX: Remove leading empty columns from ALL rows consistently
        if rows:
            # Find how many leading columns are consistently empty
            leading_empty_cols = 0
            for col_idx in range(len(rows[0])):
                if all(row[col_idx] is None or not str(row[col_idx]).strip() 
                    for row in rows if col_idx < len(row)):
                    leading_empty_cols += 1
                else:
                    break
            
            # Remove leading empty columns from all rows
            if leading_empty_cols > 0:
                rows = [row[leading_empty_cols:] for row in rows]
                if self.debug:
                    print(f"Removed {leading_empty_cols} leading empty columns")
        
        print(f"Cleaned rows (first 30):")
        for i, row in enumerate(rows[:30]):
            print(f"  Row {i:2d}: {row}")
        
        if not rows:
            return None
        
        return {
            "rows": rows,
            "sheet_name": sheet_name,
            "total_rows": len(rows),
            "total_cols": len(rows[0]) if rows else 0
        }
    
    def get_sheet_info(self) -> Dict[str, Any]:
        """Get sheet information"""
        info = {
            "file_format": self.file_extension,
            "total_sheets": len(self.pd_sheets),
            "sheet_names": list(self.pd_sheets.keys()),
            "sheets_info": {}
        }
        
        for sheet_name, df in self.pd_sheets.items():
            info["sheets_info"][sheet_name] = {
                "rows": len(df),
                "cols": len(df.columns),
                "has_data": not df.empty
            }
        
        return info


def test_excel_extractor(excel_path: str):
    """Test function"""
    print(f"Testing Excel extraction for: {excel_path}")
    
    try:
        extractor = ExcelExtractor(excel_path)
        
        # Show sheet info
        info = extractor.get_sheet_info()
        print(f"\nSheet info: {info}")
        
        # Extract text pages
        text_pages = extractor.extract_text_pages()
        print(f"\nExtracted {len(text_pages)} text pages")
        
        if text_pages:
            print(f"\nSample text from first page:")
            sample_text = text_pages[0]["text"]
            print(sample_text[:800] + "..." if len(sample_text) > 800 else sample_text)
        
        # Extract tables
        tables = extractor.extract_tables()
        print(f"\nExtracted {len(tables)} tables")
        
        if tables:
            print(f"\nSample table structure:")
            print(f"Rows: {tables[0]['total_rows']}, Cols: {tables[0]['total_cols']}")
            print(f"First few rows:")
            for i, row in enumerate(tables[0]['rows'][:5]):
                print(f"  Row {i}: {row}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_excel_extractor(sys.argv[1])
    else:
        print("Usage: python excel_extractor.py <excel_file_path>")