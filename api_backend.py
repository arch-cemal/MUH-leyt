
# ============================================================
# FASTAPI BACKEND - REST API
# ============================================================

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

app = FastAPI(
    title="نظام توليف وقص الحديد الذكي",
    description="API متكامل لإدارة عمليات تقطيع الحديد",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# PYDANTIC MODELS
# ============================================================

class PieceInput(BaseModel):
    name: str
    length: float
    quantity: int = 1
    piece_type: str

class StockInput(BaseModel):
    length: float
    bar_type: str
    quantity: int = 999999

class OptimizeRequest(BaseModel):
    project_id: Optional[int] = None
    pieces: List[PieceInput]
    stock_bars: List[StockInput]
    use_inventory: bool = True
    max_joins: int = 2

class InventoryItemInput(BaseModel):
    name: str
    length: float
    piece_type: str
    quantity: int = 1
    source_cut_id: Optional[int] = None

class ProjectInput(BaseModel):
    project_name: str
    client_name: Optional[str] = None
    notes: Optional[str] = None

# ============================================================
# API ENDPOINTS - OPTIMIZATION
# ============================================================

@app.post("/api/v1/optimize", response_model=dict)
async def optimize_cutting(request: OptimizeRequest):
    """تشغيل التوليف الأمثل"""
    try:
        # تحويل المدخلات
        requirements = [
            RequiredPiece(p.name, p.length, p.quantity, p.piece_type)
            for p in request.pieces
        ]

        stock = [
            StockBar(s.length, s.bar_type, s.quantity)
            for s in request.stock_bars
        ]

        # الحصول على المخزن
        db = DatabaseManager()
        inv_manager = InventoryManager(db)
        inventory = inv_manager.get_available() if request.use_inventory else []

        # التحسين
        optimizer = CuttingOptimizer(stock, inventory)
        result = optimizer.optimize(requirements, use_inventory=request.use_inventory)

        # تحويل النتائج
        patterns_data = []
        for p in result['patterns']:
            patterns_data.append({
                'stock_length': p.stock_length,
                'stock_type': p.stock_type,
                'pieces': p.pieces,
                'waste': p.waste,
                'utilization': round((p.stock_length - p.waste) / p.stock_length * 100, 2)
            })

        return {
            'success': True,
            'patterns': patterns_data,
            'stats': result['stats'],
            'unassigned': result['unassigned']
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# API ENDPOINTS - INVENTORY
# ============================================================

@app.get("/api/v1/inventory")
async def get_inventory(
    piece_type: Optional[str] = None,
    available_only: bool = True
):
    """الحصول على المخزن"""
    db = DatabaseManager()
    inv_manager = InventoryManager(db)
    items = inv_manager.get_available(piece_type)

    return {
        'items': [
            {
                'id': item.id,
                'name': item.name,
                'length': item.length,
                'quantity': item.quantity,
                'is_used': item.is_used
            }
            for item in items
        ],
        'total': len(items)
    }

@app.post("/api/v1/inventory")
async def add_inventory_item(item: InventoryItemInput):
    """إضافة قطعة للمخزن"""
    db = DatabaseManager()
    inv_manager = InventoryManager(db)
    item_id = inv_manager.add_item(
        item.name, item.length, item.piece_type, 
        item.quantity, item.source_cut_id
    )
    return {'success': True, 'id': item_id}

@app.delete("/api/v1/inventory/{item_id}")
async def delete_inventory_item(item_id: int):
    """حذف قطعة من المخزن"""
    db = DatabaseManager()
    inv_manager = InventoryManager(db)
    success = inv_manager.delete_item(item_id)
    return {'success': success}

# ============================================================
# API ENDPOINTS - PROJECTS
# ============================================================

@app.post("/api/v1/projects")
async def create_project(project: ProjectInput):
    """إنشاء مشروع جديد"""
    conn = DatabaseManager().get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO projects (project_name, client_name, notes)
        VALUES (?, ?, ?)
    ''', (project.project_name, project.client_name, project.notes))

    project_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {'success': True, 'id': project_id}

@app.get("/api/v1/projects")
async def get_projects():
    """الحصول على المشاريع"""
    conn = DatabaseManager().get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM projects ORDER BY created_date DESC')
    rows = cursor.fetchall()
    conn.close()

    return {
        'projects': [
            {
                'id': row[0],
                'name': row[1],
                'client': row[2],
                'date': row[3],
                'status': row[4]
            }
            for row in rows
        ]
    }

# ============================================================
# API ENDPOINTS - ARCHIVE & SEARCH
# ============================================================

@app.get("/api/v1/archive/search")
async def search_archive(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    material_type: Optional[str] = None,
    piece_name: Optional[str] = None,
    project_id: Optional[int] = None
):
    """البحث في الأرشيف"""
    db = DatabaseManager()
    archive = ArchiveManager(db)

    results = archive.search_operations(
        str(date_from) if date_from else None,
        str(date_to) if date_to else None,
        material_type,
        piece_name,
        project_id
    )

    return {'operations': results, 'total': len(results)}

@app.get("/api/v1/reports/waste")
async def waste_report(
    date_from: date = Query(...),
    date_to: date = Query(...)
):
    """تقرير الهدر"""
    db = DatabaseManager()
    reports = ReportsEngine(db)

    report = reports.generate_waste_report(str(date_from), str(date_to))
    return report

@app.get("/api/v1/reports/inventory")
async def inventory_report():
    """تقرير المخزن"""
    db = DatabaseManager()
    reports = ReportsEngine(db)

    report = reports.generate_inventory_report()
    return report

# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health_check():
    return {'status': 'healthy', 'version': '1.0.0'}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
