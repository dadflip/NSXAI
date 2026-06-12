import React, { useState, useEffect, useRef } from 'react';
import { Database, Search, Plus, Loader2, Save, Play, ChevronLeft, ChevronRight, Edit2, RefreshCw, FlaskConical, Check, X, Copy, Download, Zap } from 'lucide-react';
import { fetchMatrixColumns, fetchMatrixRows, fetchMatrixCells, updateMatrixCell, addEntity, clearMatrixCache } from '../lib/sparqlQueries';
import { fetchApi } from '../lib/apiClient';
import { apiUrl } from '../config';
import { CellEditorModal } from './CellEditorModal';

export const MatrixEditor: React.FC = () => {
    // Matrix State
    const [columns, setColumns] = useState<string[]>([]);
    const [rows, setRows] = useState<string[]>([]);
    const [cells, setCells] = useState<Record<string, string>>({}); // "s_p" -> "values"
    const [totalRows, setTotalRows] = useState(0);
    
    // UI State
    const [page, setPage] = useState(0);
    const [pageSize, setPageSize] = useState(20);
    const [search, setSearch] = useState('');
    const [columnSearch, setColumnSearch] = useState('');
    const [loading, setLoading] = useState(false);
    
    const filteredColumns = columns.filter(col => col.toLowerCase().includes(columnSearch.toLowerCase()));
    
    // Editing State
    const [editingCell, setEditingCell] = useState<{ s: string, p: string } | null>(null);
    const [editValue, setEditValue] = useState('');
    const [focusedCell, setFocusedCell] = useState<{ r: number, c: number } | null>(null);

    // Modal State
    const [showAddModal, setShowAddModal] = useState(false);
    const [newEntityUri, setNewEntityUri] = useState('http://nsxai.org/data/NewEntity');
    const [newEntityType, setNewEntityType] = useState('http://nsxai.org/ontology#Learner');

    // Scenario State
    const [simulationMode, setSimulationMode] = useState(false);
    const [pendingChanges, setPendingChanges] = useState<Record<string, { s: string, p: string, value: string }>>({});

    const tableContainerRef = useRef<HTMLDivElement>(null);

    // Initial load
    useEffect(() => {
        loadData();
    }, [page, pageSize, search]);

    const loadData = async (forceRefresh = false) => {
        setLoading(true);
        try {
            if (forceRefresh) {
                clearMatrixCache();
            }

            // 1. Fetch columns
            const cols = await fetchMatrixColumns(forceRefresh);
            setColumns(cols);

            // 2. Fetch rows for current page
            const { rows: r, total } = await fetchMatrixRows(page, pageSize, search, forceRefresh);
            setRows(r);
            setTotalRows(total);

            // 3. Fetch cells for these rows
            const cellData = await fetchMatrixCells(r, forceRefresh);
            const newCells: Record<string, string> = {};
            cellData.forEach(c => {
                newCells[`${c.s}_${c.p}`] = c.values;
            });
            setCells(newCells);
            setFocusedCell(null);

        } catch (e) {
            console.error("Error loading matrix", e);
        } finally {
            setLoading(false);
        }
    };

    const handleCellDoubleClick = (s: string, p: string) => {
        setEditingCell({ s, p });
        const cellKey = `${s}|||${p}`;
        const val = pendingChanges[cellKey] ? pendingChanges[cellKey].value : (cells[`${s}_${p}`] || '');
        setEditValue(val);
    };

    const handleCellSave = async (newValue: string) => {
        if (!editingCell) return;
        const { s, p } = editingCell;
        const cellKey = `${s}|||${p}`;
        const legacyCellKey = `${s}_${p}`;
        
        if (simulationMode) {
            setPendingChanges(prev => ({ ...prev, [cellKey]: { s, p, value: newValue } }));
            setEditingCell(null);
        } else {
            // Optimistic update
            const oldValue = cells[legacyCellKey];
            setCells(prev => ({ ...prev, [legacyCellKey]: newValue }));
            setEditingCell(null);

            try {
                await updateMatrixCell(s, p, newValue);
            } catch (e) {
                console.error("Error updating cell", e);
                // Rollback
                setCells(prev => ({ ...prev, [legacyCellKey]: oldValue }));
                alert("Error updating cell.");
            }
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (editingCell) return; // Allow input to handle its own events
        if (!focusedCell) return;

        const { r, c } = focusedCell;

        if (e.key === 'ArrowUp') {
            e.preventDefault();
            setFocusedCell({ r: Math.max(0, r - 1), c });
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setFocusedCell({ r: Math.min(rows.length - 1, r + 1), c });
        } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            setFocusedCell({ r, c: Math.max(0, c - 1) });
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            setFocusedCell({ r, c: Math.min(filteredColumns.length - 1, c + 1) });
        } else if (e.key === 'Enter') {
            e.preventDefault();
            handleCellDoubleClick(rows[r], filteredColumns[c]);
        }
    };

    const handleAddRow = () => {
        setNewEntityUri('http://nsxai.org/data/NewEntity');
        setNewEntityType('http://nsxai.org/ontology#Learner');
        setShowAddModal(true);
    };

    const confirmAddRow = async () => {
        if (!newEntityUri || !newEntityType) return;
        try {
            await addEntity(newEntityUri, newEntityType);
            setShowAddModal(false);
            loadData();
        } catch (e) {
            alert("Error adding entity.");
        }
    };

    const handleCommitSimulation = async () => {
        setLoading(true);
        try {
            const changes = Object.values(pendingChanges) as Array<{ s: string, p: string, value: string }>;
            for (const change of changes) {
                await updateMatrixCell(change.s, change.p, change.value);
            }
            setPendingChanges({});
            loadData(true);
        } catch (e) {
            console.error("Error committing simulation", e);
            alert("Error applying scenario.");
        } finally {
            setLoading(false);
        }
    };

    const [showDuplicateModal, setShowDuplicateModal] = useState(false);
    const [duplicateCount, setDuplicateCount] = useState(1);
    const [duplicating, setDuplicating] = useState(false);

    const handleExport = () => {
        window.open(apiUrl('/api/export/dataset'), '_blank');
    };

    const handleDuplicate = async () => {
        if (!focusedCell) {
            alert("Please select a cell/row first to duplicate it.");
            return;
        }
        if (duplicateCount <= 0 || duplicateCount > 500) {
            alert("Please select a number between 1 and 500.");
            return;
        }
        
        const sourceUri = rows[focusedCell.r];
        setDuplicating(true);
        try {
            const response = await fetchApi('/api/dataset/duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_uri: sourceUri, count: duplicateCount })
            });
            
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Duplication failed');
            }
            
            setShowDuplicateModal(false);
            loadData(true); // reload to show new synthetic entities
        } catch (err: any) {
            alert("Error duplicating row: " + err.message);
        } finally {
            setDuplicating(false);
        }
    };

    const totalPages = Math.ceil(totalRows / pageSize);

    return (
        <div className="h-full flex flex-col gap-2">
            
            {/* Matrix Container */}
            <div className="flex-1 flex flex-col bg-slate-50 border border-slate-300 overflow-hidden min-h-0">
                
                {/* Toolbar */}
                <div className="p-2 border-b border-slate-300 flex items-center justify-between bg-slate-200 overflow-x-auto">
                    <div className="flex items-center gap-2 shrink-0">
                        <div className="flex gap-2">
                            <div className="relative">
                                <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
                                <input 
                                    type="text"
                                    placeholder="Search entity..."
                                    value={search}
                                    onChange={e => { setPage(0); setSearch(e.target.value); }}
                                    className="pl-7 pr-2 py-1.5 bg-white border border-slate-300 rounded-sm text-xs text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 w-48 transition-colors"
                                />
                            </div>
                            <div className="relative">
                                <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
                                <input 
                                    type="text"
                                    placeholder="Filter columns..."
                                    value={columnSearch}
                                    onChange={e => setColumnSearch(e.target.value)}
                                    className="pl-7 pr-2 py-1.5 bg-white border border-slate-300 rounded-sm text-xs text-slate-800 placeholder:text-slate-400 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 w-48 transition-colors"
                                />
                            </div>
                        </div>
                        <button 
                            onClick={() => loadData(true)}
                            className="flex items-center gap-1 px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 rounded-sm text-xs border border-slate-300"
                            title="Refresh and clear cache"
                        >
                            <RefreshCw className={`w-3 h-3 text-slate-500 ${loading ? 'animate-spin' : ''}`} /> Refresh
                        </button>
                        <button 
                            onClick={handleAddRow}
                            className="flex items-center gap-1 px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 rounded-sm text-xs border border-slate-300"
                            title="Add a new entity manually"
                        >
                            <Plus className="w-3 h-3 text-slate-500" /> Entity
                        </button>
                        
                        <div className="flex items-center gap-1 border-l border-slate-300 pl-2 ml-1">
                            <button 
                                onClick={handleExport}
                                className="flex items-center gap-1 px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 rounded-sm text-xs border border-slate-300"
                                title="Export current dataset as CSV"
                            >
                                <Download className="w-3 h-3 text-slate-500" /> Export CSV
                            </button>
                            <button 
                                onClick={() => setShowDuplicateModal(true)}
                                disabled={!focusedCell}
                                className={`flex items-center gap-1 px-2 py-1 rounded-sm text-xs border ${!focusedCell ? 'bg-slate-50 border-slate-200 text-slate-400 cursor-not-allowed' : 'bg-white hover:bg-slate-100 text-slate-700 border-slate-300'}`}
                                title={!focusedCell ? "Select a row to duplicate" : "Duplicate selected row"}
                            >
                                <Copy className={`w-3 h-3 ${!focusedCell ? 'text-slate-300' : 'text-blue-500'}`} /> Duplicate Row
                            </button>
                        </div>

                        <div className="flex items-center gap-1 border-l border-slate-300 pl-2 ml-1">
                            <button 
                                onClick={() => setSimulationMode(!simulationMode)}
                                className={`flex items-center gap-1 px-2 py-1 rounded-sm text-xs border ${simulationMode ? 'bg-yellow-100 text-yellow-800 border-yellow-300 font-bold' : 'bg-white hover:bg-slate-100 text-slate-700 border-slate-300'}`}
                                title="Enable Simulation mode (Drafting)"
                            >
                                <FlaskConical className="w-3 h-3" /> Scenario
                            </button>
                            
                            {simulationMode && Object.keys(pendingChanges).length > 0 && (
                                <>
                                    <button 
                                        onClick={handleCommitSimulation}
                                        className="flex items-center gap-1 px-2 py-1 bg-green-50 hover:bg-green-100 text-green-700 rounded-sm text-xs border border-green-300 font-bold"
                                    >
                                        <Check className="w-3 h-3" /> Apply
                                    </button>
                                    <button 
                                        onClick={() => setPendingChanges({})}
                                        className="flex items-center gap-1 px-2 py-1 bg-red-50 hover:bg-red-100 text-red-700 rounded-sm text-xs border border-red-300"
                                    >
                                        <X className="w-3 h-3" /> Cancel
                                    </button>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Pagination */}
                    <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs text-slate-600 font-mono">
                            {totalRows > 0 ? `${page * pageSize + 1}-${Math.min((page + 1) * pageSize, totalRows)}/${totalRows}` : '0 results'}
                        </span>
                        <div className="flex gap-0.5">
                            <button 
                                onClick={() => setPage(p => Math.max(0, p - 1))}
                                disabled={page === 0}
                                className="p-1 rounded-sm bg-white border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-30"
                            >
                                <ChevronLeft className="w-3 h-3" />
                            </button>
                            <button 
                                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                                disabled={page >= totalPages - 1 || totalPages === 0}
                                className="p-1 rounded-sm bg-white border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-30"
                            >
                                <ChevronRight className="w-3 h-3" />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Table */}
                <div 
                    ref={tableContainerRef}
                    className="flex-1 overflow-auto bg-white outline-none"
                    tabIndex={0}
                    onKeyDown={handleKeyDown}
                >
                    {loading && (
                        <div className="absolute inset-0 z-20 bg-white/50 flex items-center justify-center">
                            <Loader2 className="w-6 h-6 text-slate-500 animate-spin" />
                        </div>
                    )}
                    <table className="w-full text-left border-collapse min-w-max text-[11px]">
                        <thead className="sticky top-0 bg-slate-100 z-30 border-b border-slate-300">
                            <tr>
                                <th className="px-2 py-1 font-bold text-slate-700 border-r border-b border-slate-300 sticky left-0 bg-slate-100 z-40 min-w-[150px]">
                                    Entity (Source)
                                </th>
                                {filteredColumns.map(col => (
                                    <th key={col} className="px-2 py-1 font-bold text-slate-700 border-r border-b border-slate-300 truncate max-w-[150px]" title={col}>
                                        {col.split(/[/#]/).pop()}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((row, rIndex) => (
                                <tr key={row} className="hover:bg-blue-50 transition-colors group">
                                    <td className="px-2 py-1 border-r border-b border-slate-200 sticky left-0 bg-white group-hover:bg-blue-50 z-20 font-mono text-slate-800 font-bold max-w-[150px]" title={row}>
                                        <div className="flex items-center justify-between gap-1">
                                            <span className="truncate">{row.split(/[/#]/).pop()}</span>
                                            <button 
                                                onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(row); }}
                                                className="hover:text-blue-600 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-slate-400"
                                                title="Copy entity URI"
                                            >
                                                <Copy className="w-3 h-3" />
                                            </button>
                                        </div>
                                    </td>
                                    {filteredColumns.map((col, cIndex) => {
                                        const pendingKey = `${row}|||${col}`;
                                        const legacyKey = `${row}_${col}`;
                                        const pending = pendingChanges[pendingKey];
                                        const isModified = !!pending;
                                        const val = isModified ? pending.value : (cells[legacyKey] || '');
                                        
                                        const isEditing = editingCell?.s === row && editingCell?.p === col;
                                        const isFocused = focusedCell?.r === rIndex && focusedCell?.c === cIndex;
                                        
                                        let cellClass = "px-2 py-1 border-r border-b border-slate-200 min-w-[100px] max-w-[200px] relative group/cell cursor-pointer ";
                                        if (isFocused) cellClass += "bg-blue-100 outline outline-1 outline-blue-400 outline-offset-[-1px] ";
                                        else if (isModified) cellClass += "bg-yellow-50 ";
                                        else cellClass += "bg-white ";
                                        
                                        return (
                                            <td 
                                                key={col} 
                                                className={cellClass}
                                                onClick={() => setFocusedCell({ r: rIndex, c: cIndex })}
                                                onDoubleClick={() => handleCellDoubleClick(row, col)}
                                            >
                                                <div className="flex items-center justify-between">
                                                    <div className="truncate text-slate-600 font-mono" title={val}>
                                                        {val ? val.split('|').map((v, i) => (
                                                            <span key={i} className={`inline-flex items-center gap-0.5 px-1 py-0.5 mr-0.5 mb-0.5 max-w-full ${isModified ? 'bg-yellow-100 text-yellow-800 border border-yellow-200' : 'text-slate-800'}`}>
                                                                <span className="truncate">{v.split(/[/#]/).pop() || v}</span>
                                                            </span>
                                                        )) : <span className="text-slate-300">-</span>}
                                                    </div>
                                                    <Edit2 className="w-3 h-3 text-slate-400 opacity-0 group-hover/cell:opacity-100 transition-opacity shrink-0" />
                                                </div>
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                            {rows.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={filteredColumns.length + 1} className="px-4 py-8 text-center text-slate-500 bg-white font-medium">
                                        No entities found.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
            {/* Add Entity Modal */}
            {showAddModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
                    <div className="bg-slate-50 border border-slate-300 shadow-xl p-4 w-[400px]">
                        <h3 className="text-sm font-bold text-slate-800 mb-3 border-b border-slate-200 pb-2">Add Entity</h3>
                        
                        <div className="space-y-3">
                            <div>
                                <label className="block text-[11px] font-bold text-slate-600 mb-1 uppercase">New entity URI</label>
                                <input 
                                    type="text" 
                                    value={newEntityUri}
                                    onChange={e => setNewEntityUri(e.target.value)}
                                    className="w-full bg-white border border-slate-300 px-2 py-1 text-xs text-slate-800 outline-none focus:border-blue-400"
                                    placeholder="http://nsxai.org/data/NewEntity"
                                    autoFocus
                                />
                            </div>
                            <div>
                                <label className="block text-[11px] font-bold text-slate-600 mb-1 uppercase">Type URI</label>
                                <input 
                                    type="text" 
                                    value={newEntityType}
                                    onChange={e => setNewEntityType(e.target.value)}
                                    className="w-full bg-white border border-slate-300 px-2 py-1 text-xs text-slate-800 outline-none focus:border-blue-400"
                                    placeholder="http://nsxai.org/ontology#Learner"
                                />
                            </div>
                        </div>

                        <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-slate-200">
                            <button 
                                onClick={() => setShowAddModal(false)}
                                className="px-3 py-1 bg-white border border-slate-300 text-xs font-bold text-slate-600 hover:bg-slate-100"
                            >
                                Cancel
                            </button>
                            <button 
                                onClick={confirmAddRow}
                                className="px-3 py-1 bg-blue-100 border border-blue-300 text-xs font-bold text-blue-800 hover:bg-blue-200 flex items-center gap-1"
                            >
                                <Plus className="w-3 h-3" /> Add
                            </button>
                        </div>
                    </div>
                </div>
            )}
            
            {/* Cell Editor Modal */}
            {editingCell && (
                <CellEditorModal 
                    initialValue={editValue}
                    subjectUri={editingCell.s}
                    predicateUri={editingCell.p}
                    onSave={handleCellSave}
                    onCancel={() => setEditingCell(null)}
                />
            )}

            {/* Duplicate Row Modal */}
            {showDuplicateModal && focusedCell && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
                    <div className="bg-slate-50 border border-slate-300 shadow-xl p-4 w-[400px]">
                        <h3 className="text-sm font-bold text-slate-800 mb-3 border-b border-slate-200 pb-2 flex items-center gap-2">
                            <Copy className="w-4 h-4 text-blue-500" />
                            Duplicate Row
                        </h3>
                        
                        <div className="space-y-3 mb-4">
                            <p className="text-xs text-slate-600">
                                This will generate exact identical copies of the entity <br/>
                                <strong className="break-all font-mono text-[10px] bg-slate-200 px-1">{rows[focusedCell.r]}</strong> <br/>
                                with suffixed URIs (`_1`, `_2`, etc.).
                            </p>
                            <div>
                                <label className="block text-[11px] font-bold text-slate-600 mb-1 uppercase">Number of copies</label>
                                <input 
                                    type="number" 
                                    min="1"
                                    max="500"
                                    value={duplicateCount}
                                    onChange={e => setDuplicateCount(parseInt(e.target.value) || 0)}
                                    className="w-full bg-white border border-slate-300 px-2 py-1 text-xs text-slate-800 outline-none focus:border-blue-400"
                                    autoFocus
                                    disabled={duplicating}
                                />
                            </div>
                        </div>

                        <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
                            <button 
                                onClick={() => setShowDuplicateModal(false)}
                                disabled={duplicating}
                                className="px-3 py-1 bg-white border border-slate-300 text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                            >
                                Cancel
                            </button>
                            <button 
                                onClick={handleDuplicate}
                                disabled={duplicating}
                                className="px-3 py-1 bg-blue-100 border border-blue-300 text-xs font-bold text-blue-800 hover:bg-blue-200 flex items-center gap-1 disabled:opacity-50"
                            >
                                {duplicating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Copy className="w-3 h-3" />}
                                {duplicating ? 'Duplicating...' : 'Duplicate'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
