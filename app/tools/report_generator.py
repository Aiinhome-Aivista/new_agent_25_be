import io
from datetime import datetime
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    pass  # Allow tests/imports to pass if python-docx isn't installed in environment

class DocxReportGenerator:
    """Generates deterministic Word document (.docx) reports for code reviews."""

    @staticmethod
    def generate_report(review_data: dict) -> io.BytesIO:
        """
        Creates a Word document from review_data dictionary and returns it as an in-memory BytesIO buffer.
        """
        doc = Document()
        
        # Title
        title = doc.add_heading('AI Code Review Report', level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Metadata
        doc.add_heading('Review Metadata', level=2)
        meta_table = doc.add_table(rows=0, cols=2)
        meta_table.style = 'Table Grid'
        
        session = review_data.get('session', {})
        metadata_items = [
            ("Review Session ID", session.get('id', 'N/A')),
            ("Repository", session.get('repository_name', 'N/A')),
            ("Branch", session.get('branch', 'N/A')),
            ("Language", session.get('language', 'N/A')),
            ("Author", session.get('author', 'N/A')),
            ("Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]
        
        for k, v in metadata_items:
            row_cells = meta_table.add_row().cells
            row_cells[0].text = k
            row_cells[1].text = str(v)
            
        # Executive Summary
        doc.add_heading('Executive Summary', level=2)
        doc.add_paragraph(review_data.get('summary', 'No summary available.'))
        
        # Push Readiness & Risk
        doc.add_heading('Assessment Status', level=2)
        status_p = doc.add_paragraph()
        status_p.add_run('Push Readiness: ').bold = True
        status_p.add_run(str(review_data.get('pushReadiness', 'UNKNOWN')))
        
        risk_p = doc.add_paragraph()
        risk_p.add_run('Risk Level: ').bold = True
        risk_p.add_run(str(review_data.get('riskLevel', 'UNKNOWN')))
        
        # Acceptance Criteria
        ac_results = review_data.get('acceptanceCriteriaResults', [])
        if ac_results:
            doc.add_heading('Acceptance Criteria Verification', level=2)
            ac_table = doc.add_table(rows=1, cols=3)
            ac_table.style = 'Table Grid'
            hdr_cells = ac_table.rows[0].cells
            hdr_cells[0].text = 'Criteria'
            hdr_cells[1].text = 'Status'
            hdr_cells[2].text = 'Reasoning'
            
            for ac in ac_results:
                row_cells = ac_table.add_row().cells
                desc = ac.get('description', '')
                criteria = f"{ac.get('criterion_id', 'AC')}: {desc}" if ac.get('criterion_id') else desc
                status = 'Satisfied' if ac.get('is_satisfied') else 'Unmet'
                row_cells[0].text = str(criteria)
                row_cells[1].text = status
                row_cells[2].text = str(ac.get('evidence', ''))
                
        # Findings / Issues
        issues = review_data.get('issues', [])
        if issues:
            doc.add_heading('Findings and Issues', level=2)
            issues_table = doc.add_table(rows=1, cols=5)
            issues_table.style = 'Table Grid'
            hdr_cells = issues_table.rows[0].cells
            hdr_cells[0].text = 'Severity'
            hdr_cells[1].text = 'Category'
            hdr_cells[2].text = 'File : Line'
            hdr_cells[3].text = 'Message'
            hdr_cells[4].text = 'Suggestion'
            
            for issue in issues:
                row_cells = issues_table.add_row().cells
                row_cells[0].text = str(issue.get('severity', ''))
                row_cells[1].text = str(issue.get('category', ''))
                row_cells[2].text = f"{issue.get('file', '')} : {issue.get('line', '')}"
                row_cells[3].text = str(issue.get('message', ''))
                row_cells[4].text = str(issue.get('suggestion', ''))
                
        # Missing Tests
        missing_tests = review_data.get('missingTests', [])
        if missing_tests:
            doc.add_heading('Missing Tests', level=2)
            for mt in missing_tests:
                mt_p = doc.add_paragraph(style='List Bullet')
                mt_p.add_run(f"[{mt.get('test_type', 'Test')}] ").bold = True
                mt_p.add_run(mt.get('description', ''))
                
        # Passed Checks
        passed_checks = review_data.get('passedChecks', [])
        if passed_checks:
            doc.add_heading('Passed Checks', level=2)
            for pc in passed_checks:
                pc_p = doc.add_paragraph(style='List Bullet')
                pc_p.add_run(pc.get('description', ''))
                
        # Save to buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
