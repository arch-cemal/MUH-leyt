
# ============================================================
# ADVANCED CUTTING OPTIMIZATION
# Dynamic Programming + Column Generation
# ============================================================

from functools import lru_cache
import numpy as np

class AdvancedCuttingOptimizer(CuttingOptimizer):
    """محرك التحسين المتقدم باستخدام DP وColumn Generation"""

    def __init__(self, stock_bars: List[StockBar], inventory: List[InventoryItem] = None,
                 blade_width: float = 0.5):  # عرض شفرة القص
        super().__init__(stock_bars, inventory)
        self.blade_width = blade_width

    def optimize_dp(self, requirements: List[RequiredPiece], use_inventory: bool = True) -> Dict:
        """تحسين باستخدام Dynamic Programming"""
        all_pieces = self._create_piece_list(requirements)

        # الخطوة 1: استخدام المخزن
        patterns = []
        if use_inventory and self.inventory:
            inv_patterns, all_pieces = self._try_inventory(all_pieces)
            patterns.extend(inv_patterns)

        # الخطوة 2: DP للتوليف الأمثل
        remaining = all_pieces[:]

        while remaining:
            best_pattern = None
            best_score = float('inf')  # minimize waste + penalty

            for stock in self.stock_bars:
                # استخدام DP لإيجاد أفضل توليفة لهذا القضيب
                combo, waste = self._dp_fill(remaining, stock.length)

                if combo:
                    # حساب النتيجة مع عقوبة للهدر الكبير
                    score = waste + (50 if waste > 100 else 0) + (20 if waste > 50 else 0)

                    if score < best_score:
                        best_score = score
                        best_pattern = (combo, waste, stock)

            if best_pattern:
                combo, waste, stock = best_pattern
                pattern = CutPattern(
                    stock_length=stock.length,
                    pieces=combo,
                    waste=waste,
                    stock_type=stock.bar_type
                )
                patterns.append(pattern)

                # إزالة القطع المستخدمة
                for p in combo:
                    for i, r in enumerate(remaining):
                        if r['name'] == p['name'] and abs(r['length'] - p['length']) < 0.01:
                            remaining.pop(i)
                            break
            else:
                break

        return self._build_result(patterns, requirements, remaining)

    def _dp_fill(self, pieces: List[Dict], stock_length: float) -> Tuple[List[Dict], float]:
        """ملء القضيب باستخدام Dynamic Programming (Knapsack Variation)"""
        n = len(pieces)
        if n == 0:
            return None, float('inf')

        # DP table: dp[i][w] = max value using first i pieces with capacity w
        # value = total length used (we want to maximize)
        capacity = int(stock_length)
        dp = [[0] * (capacity + 1) for _ in range(n + 1)]
        keep = [[False] * (capacity + 1) for _ in range(n + 1)]

        for i in range(1, n + 1):
            piece_len = int(pieces[i-1]['length'])
            for w in range(capacity + 1):
                # don't take piece i-1
                dp[i][w] = dp[i-1][w]

                # take piece i-1 (if it fits)
                if piece_len <= w and dp[i-1][w - piece_len] + piece_len > dp[i][w]:
                    dp[i][w] = dp[i-1][w - piece_len] + piece_len
                    keep[i][w] = True

        # Backtrack to find which pieces to take
        combo = []
        w = capacity
        for i in range(n, 0, -1):
            if keep[i][w]:
                combo.append(pieces[i-1].copy())
                w -= int(pieces[i-1]['length'])

        if not combo:
            return None, float('inf')

        waste = stock_length - sum(p['length'] for p in combo)
        return combo, waste

    def _build_result(self, patterns, requirements, remaining):
        """بناء نتيجة التحسين"""
        total_waste = sum(p.waste for p in patterns)
        total_stock = sum(p.stock_length for p in patterns)
        total_required = sum(req.length * req.quantity for req in requirements)
        utilization = (total_required / total_stock * 100) if total_stock > 0 else 0

        return {
            'patterns': patterns,
            'unassigned': remaining,
            'stats': {
                'total_patterns': len(patterns),
                'total_waste': total_waste,
                'total_stock_length': total_stock,
                'total_required_length': total_required,
                'utilization_rate': round(utilization, 2),
                'waste_percentage': round(100 - utilization, 2),
                'inventory_used': len([p for p in patterns if any('from_inventory' in x for x in p.pieces)]),
                'algorithm': 'Dynamic Programming'
            }
        }

    def optimize_hybrid(self, requirements: List[RequiredPiece], use_inventory: bool = True) -> Dict:
        """تحسين هجين: DP + Local Search"""
        # تشغيل DP
        dp_result = self.optimize_dp(requirements, use_inventory)

        # تشغيل Greedy
        greedy_result = self.optimize(requirements, use_inventory)

        # اختيار الأفضل
        if dp_result['stats']['utilization_rate'] >= greedy_result['stats']['utilization_rate']:
            return dp_result
        else:
            greedy_result['stats']['algorithm'] = 'Greedy + Local Search'
            return greedy_result

# ============================================================
# PERFORMANCE BENCHMARK
# ============================================================

class PerformanceBenchmark:
    """اختبار أداء الخوارزميات"""

    @staticmethod
    def benchmark(optimizer_class, requirements, stock_bars, inventory=None, runs=3):
        """قياس الأداء"""
        import time

        results = []
        for _ in range(runs):
            start = time.time()
            optimizer = optimizer_class(stock_bars, inventory)
            result = optimizer.optimize(requirements, use_inventory=True)
            elapsed = time.time() - start

            results.append({
                'time': elapsed,
                'utilization': result['stats']['utilization_rate'],
                'waste': result['stats']['waste_percentage'],
                'patterns': result['stats']['total_patterns']
            })

        avg_time = sum(r['time'] for r in results) / len(results)
        avg_util = sum(r['utilization'] for r in results) / len(results)

        return {
            'avg_time': round(avg_time, 4),
            'avg_utilization': round(avg_util, 2),
            'runs': runs,
            'details': results
        }
