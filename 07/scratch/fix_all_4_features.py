import os
import re

FRONTEND_DIR = r"f:\7th semester\FYP\deepguard\frontend"
BACKEND_DIR = r"f:\7th semester\FYP\deepguard\backend"

def fix_history_pdf():
    filepath = os.path.join(FRONTEND_DIR, "history.html")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Add jsPDF scripts
    if "jspdf.umd.min.js" not in content:
        scripts = """
    <!-- jsPDF for PDF Export -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.5.31/jspdf.plugin.autotable.min.js"></script>
"""
        content = content.replace("<!-- Scripts -->", "<!-- Scripts -->" + scripts)

    # Add exportPDF function
    if "function exportPDF()" not in content:
        export_func = """
        function exportPDF() {
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF();
            
            // Header
            doc.setFontSize(20);
            doc.setTextColor(108, 99, 255);
            doc.text('DeepGuard - Detection Report', 14, 20);
            
            doc.setFontSize(10);
            doc.setTextColor(100);
            doc.text('Generated: ' + new Date().toLocaleString(), 14, 28);
            doc.text('User: ' + localStorage.getItem('userName'), 14, 34);
            
            // Table
            const tableData = detectionHistory.map(d => [
                new Date(d.created_at).toLocaleDateString(),
                d.category || 'General',
                d.result,
                d.confidence + '%',
                d.explanation?.substring(0, 50) + '...'
            ]);
            
            doc.autoTable({
                startY: 40,
                head: [['Date', 'Category', 'Result', 'Confidence', 'AI Analysis']],
                body: tableData,
                headStyles: { fillColor: [108, 99, 255], textColor: 255 },
                alternateRowStyles: { fillColor: [245, 245, 255] },
                styles: { fontSize: 8 }
            });
            
            // Footer
            const pageCount = doc.internal.getNumberOfPages();
            for(let i = 1; i <= pageCount; i++) {
                doc.setPage(i);
                doc.setFontSize(8);
                doc.setTextColor(150);
                doc.text(
                'DeepGuard - AI Fake Product Detection | MUET Jamshoro | Page ' + i,
                14,
                doc.internal.pageSize.height - 10
                );
            }
            
            doc.save('DeepGuard-Report-' + new Date().toISOString().split('T')[0] + '.pdf');
        }
        """
        # Insert before closing script tag or at end of existing script block
        content = content.replace("async function logout()", export_func + "\n        async function logout()")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed history.html PDF export")

def create_reports_backend():
    # 1. create routes/reports.py
    code = """from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.report import Report
from models.user import User
from routes.detection import get_current_user

router = APIRouter()

@router.post("/submit")
def submit_report(
    report_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    report = Report(
        user_id=current_user.id,
        product_name=report_data.get("product_name"),
        # We need to map category from the model schema
        description=report_data.get("description"),
        product_url=report_data.get("product_url"),
        status="Pending"
    )
    db.add(report)
    db.commit()
    return {"message": "Report submitted successfully"}

@router.get("/all")
def get_all_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return reports
"""
    reports_py = os.path.join(BACKEND_DIR, "routes", "reports.py")
    with open(reports_py, "w", encoding="utf-8") as f:
        f.write(code)
    
    # 2. Update main.py
    main_py = os.path.join(BACKEND_DIR, "main.py")
    with open(main_py, "r", encoding="utf-8") as f:
        main_content = f.read()
    
    if "from routes import auth, admin, detection as detection_route, chat, reports" not in main_content:
        main_content = main_content.replace(
            "from routes import auth, admin, detection as detection_route, chat",
            "from routes import auth, admin, detection as detection_route, chat, reports"
        )
        main_content = main_content.replace(
            "app.include_router(chat.router, prefix=\"/api/chat\", tags=[\"Chat\"])",
            "app.include_router(chat.router, prefix=\"/api/chat\", tags=[\"Chat\"])\napp.include_router(reports.router, prefix=\"/api/reports\", tags=[\"Reports\"])"
        )
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(main_content)
    
    print("Created backend reports API")

def create_report_frontend():
    code = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Fake Product - DeepGuard</title>
    <link rel="stylesheet" href="css/style.css?v=1785129584">
    <style>
        .report-form { max-width: 600px; margin: 2rem auto; background: var(--bg-card); padding: 2rem; border-radius: 12px; border: 1px solid var(--border-color); }
    </style>
</head>
<body>
    <header class="navbar">
        <div class="logo">DeepGuard</div>
        <nav class="nav-links">
            <a href="dashboard.html">Dashboard</a>
            <a href="detect.html">Detect</a>
            <a href="history.html">History</a>
            <a href="report.html" class="active">Report Fake</a>
        </nav>
        <div class="user-menu" style="color:white" onclick="logout()">Logout</div>
    </header>

    <main class="container" style="padding-top: 6rem;">
        <h1 style="text-align:center">Report a Fake Product</h1>
        <p style="text-align:center; color: var(--text-secondary);">Help us improve by reporting fake products you encountered.</p>

        <div class="report-form">
            <form id="reportForm">
                <div class="form-group">
                    <label class="form-label" for="productName">Product Name</label>
                    <input type="text" id="productName" class="form-input" required placeholder="e.g. Nike Air Max 90">
                </div>
                
                <div class="form-group">
                    <label class="form-label" for="category">Category</label>
                    <select id="category" class="form-input" required>
                        <option value="Electronics">Electronics</option>
                        <option value="Footwear">Footwear</option>
                        <option value="Medicine">Medicine</option>
                        <option value="Cosmetics">Cosmetics</option>
                        <option value="Other">Other</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label class="form-label" for="productUrl">Product URL (optional)</label>
                    <input type="url" id="productUrl" class="form-input" placeholder="https://example.com/product">
                </div>
                
                <div class="form-group">
                    <label class="form-label" for="description">Description</label>
                    <textarea id="description" class="form-input" rows="4" required placeholder="Why do you think it's fake?"></textarea>
                </div>
                
                <button type="submit" class="btn btn-primary" style="width:100%">Submit Report</button>
            </form>
        </div>
    </main>

    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
    <script>
        if (!localStorage.getItem('token')) { window.location.href = 'login.html'; }
        const API_BASE_URL = localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api';

        function logout() {
            localStorage.clear();
            window.location.href = 'login.html';
        }

        document.getElementById('reportForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = {
                product_name: document.getElementById('productName').value,
                category: document.getElementById('category').value,
                description: document.getElementById('description').value,
                product_url: document.getElementById('productUrl').value
            };
            
            const token = localStorage.getItem('token');
            
            try {
                const response = await fetch(`${API_BASE_URL}/reports/submit`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(data)
                });
                
                if(response.ok) {
                    Swal.fire('Success', 'Report submitted successfully!', 'success');
                    document.getElementById('reportForm').reset();
                } else {
                    const err = await response.json();
                    Swal.fire('Error', err.detail || 'Failed to submit', 'error');
                }
            } catch(e) {
                Swal.fire('Error', 'Server error', 'error');
            }
        });
    </script>
</body>
</html>
"""
    with open(os.path.join(FRONTEND_DIR, "report.html"), "w", encoding="utf-8") as f:
        f.write(code)
    print("Created report.html")

def create_admin_reports():
    # Create admin/reports.html
    code = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reported Products - DeepGuard Admin</title>
    <link rel="stylesheet" href="../css/style.css?v=1785129584">
    <style>
        .admin-layout { display: flex; min-height: 100vh; }
        .admin-sidebar { width: 250px; background: var(--bg-card); border-right: 1px solid var(--border-color); display: flex; flex-direction: column; }
        .admin-brand { padding: 2rem; font-size: 1.5rem; font-weight: 800; color: #fff; border-bottom: 1px solid var(--border-color); }
        .admin-nav { padding: 1rem 0; flex: 1; }
        .admin-nav a { display: flex; align-items: center; padding: 1rem 2rem; color: var(--text-secondary); text-decoration: none; transition: 0.2s; }
        .admin-nav a:hover, .admin-nav a.active { background: rgba(108, 99, 255, 0.1); color: var(--primary); border-right: 3px solid var(--primary); }
        .admin-main { flex: 1; padding: 2rem; background: var(--bg-dark); overflow-y: auto; }
        .admin-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
    </style>
</head>
<body>
    <div class="admin-layout">
        <!-- Sidebar -->
        <aside class="admin-sidebar">
            <div class="admin-brand">DeepGuard Admin</div>
            <nav class="admin-nav">
                <a href="dashboard.html">Dashboard</a>
                <a href="users.html">Users</a>
                <a href="detections.html">Detections</a>
                <a href="reports.html" class="active">Reports</a>
                <a href="settings.html">Settings</a>
            </nav>
            <div class="admin-nav" style="flex:0; border-top:1px solid var(--border-color);">
                <a href="#" onclick="logout()">Logout</a>
            </div>
        </aside>

        <!-- Main Content -->
        <main class="admin-main">
            <div class="admin-header">
                <div>
                    <h1>Reported Products</h1>
                    <p style="color: var(--text-secondary)">Manage fake products reported by users.</p>
                </div>
            </div>

            <div class="table-container">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>User ID</th>
                            <th>Product</th>
                            <th>Category</th>
                            <th>Description</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="reportsTable">
                        <!-- Filled by JS -->
                    </tbody>
                </table>
            </div>
        </main>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
    <script>
        if (!localStorage.getItem('token') || localStorage.getItem('role') !== 'admin') {
            window.location.href = '../login.html';
        }
        
        const API_BASE_URL = localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api';

        function logout() {
            localStorage.clear();
            window.location.href = '../login.html';
        }

        async function loadReports() {
            const token = localStorage.getItem('token');
            try {
                const response = await fetch(`${API_BASE_URL}/reports/all`, { 
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const reports = await response.json();
                
                const tbody = document.getElementById('reportsTable');
                tbody.innerHTML = reports.map(r => `
                    <tr>
                        <td>${new Date(r.created_at).toLocaleDateString()}</td>
                        <td>${r.user_id}</td>
                        <td>${r.product_name || 'N/A'}</td>
                        <td>${r.category || 'N/A'}</td>
                        <td title="${r.description}">${r.description?.substring(0, 50)}...</td>
                        <td>
                            <span class="badge" style="background: ${r.status === 'Pending' ? '#f59e0b' : '#10b981'}; color: white; padding: 4px 8px; border-radius: 4px;">
                                ${r.status}
                            </span>
                        </td>
                    </tr>
                `).join('');
            } catch(e) {
                console.error(e);
            }
        }

        loadReports();
    </script>
</body>
</html>
"""
    with open(os.path.join(FRONTEND_DIR, "admin", "reports.html"), "w", encoding="utf-8") as f:
        f.write(code)
    
    # Update all admin pages to include the Reports link
    admin_pages = ["dashboard.html", "detections.html", "settings.html", "users.html"]
    for page in admin_pages:
        p_path = os.path.join(FRONTEND_DIR, "admin", page)
        with open(p_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Add the Reports link if missing
        if "reports.html" not in content:
            content = content.replace(
                '<a href="detections.html">Detections</a>',
                '<a href="detections.html">Detections</a>\n                <a href="reports.html">Reports</a>'
            )
            # Also handle the case where detections.html is active
            content = content.replace(
                '<a href="detections.html" class="active">Detections</a>',
                '<a href="detections.html" class="active">Detections</a>\n                <a href="reports.html">Reports</a>'
            )
            with open(p_path, "w", encoding="utf-8") as f:
                f.write(content)
                
    print("Created admin/reports.html and updated admin navbars")

def add_mobile_css():
    css_path = os.path.join(FRONTEND_DIR, "css", "style.css")
    with open(css_path, "a", encoding="utf-8") as f:
        f.write("""

/* =========================================
   Mobile Responsiveness
========================================= */
@media (max-width: 768px) {
  /* Navbar */
  .navbar { padding: 10px 15px; }
  .nav-links { display: none; }
  
  /* Dashboard stats */
  .stats-grid { 
    grid-template-columns: 1fr 1fr !important; 
  }
  
  /* Detection page */
  .upload-zone { 
    padding: 30px 15px !important; 
  }
  
  /* Tables */
  .table-container { 
    overflow-x: auto; 
  }
  table.data-table { min-width: 600px; }
  
  /* Auth pages */
  .auth-container {
    flex-direction: column !important;
  }
  .auth-left { display: none !important; }
  .auth-right { 
    width: 100% !important;
    padding: 30px 20px !important;
  }
  
  /* Admin panel */
  .admin-layout { flex-direction: column; }
  .admin-sidebar { width: 100%; border-right: none; border-bottom: 1px solid var(--border-color); }
  .admin-nav { display: flex; overflow-x: auto; padding: 0; }
  .admin-nav a { padding: 1rem; white-space: nowrap; border-right: none; border-bottom: 3px solid transparent; }
  .admin-nav a.active { border-right: none; border-bottom: 3px solid var(--primary); }
  
  /* Cards */
  .cards-grid {
    grid-template-columns: 1fr !important;
  }
  
  /* Buttons */
  .btn { 
    width: 100%; 
    margin-bottom: 10px;
  }
}

@media (max-width: 480px) {
  .stats-grid {
    grid-template-columns: 1fr !important;
  }
  h1 { font-size: 24px !important; }
  h2 { font-size: 20px !important; }
}
""")
    print("Appended mobile CSS to style.css")

if __name__ == "__main__":
    fix_history_pdf()
    create_reports_backend()
    create_report_frontend()
    create_admin_reports()
    add_mobile_css()
    print("All features implemented successfully.")
