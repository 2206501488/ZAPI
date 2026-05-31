/**
 * MaskEditor — Full-screen mask inpainting editor using react-konva.
 *
 * Tools: Brush, Freehand Lasso, Rectangle, Ellipse, Eraser
 * Features: Undo/Redo, adjustable brush size & feather, live preview
 *
 * Performance: "drawingShape" (live) is separated from "shapes" (committed)
 * so only the current stroke triggers re-render, not the entire history.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Stage, Layer, Rect, Line, Ellipse, Image as KonvaImage } from 'react-konva';
import Konva from 'konva';
import {
    Paintbrush, Eraser, Square, Circle, Lasso,
    Undo2, Redo2, RotateCcw, X, Check,
} from 'lucide-react';

// ── Types ──────────────────────────────────────────────────────

type ToolType = 'brush' | 'eraser' | 'rect' | 'ellipse' | 'lasso';

interface DrawnLine {
    type: 'line';
    tool: 'brush' | 'eraser' | 'lasso';
    points: number[];
    strokeWidth: number;
    closed?: boolean;
}
interface DrawnRect {
    type: 'rect';
    x: number; y: number; width: number; height: number;
}
interface DrawnEllipse {
    type: 'ellipse';
    x: number; y: number; radiusX: number; radiusY: number;
}
type DrawnShape = DrawnLine | DrawnRect | DrawnEllipse;

// ── Props ──────────────────────────────────────────────────────

export interface MaskEditorProps {
    imageSrc: string;
    existingMask?: string;
    existingFeather?: number;
    onConfirm: (maskDataUrl: string, feather: number, outputSize?: string) => void;
    onCancel: () => void;
}

// ── Constants ──────────────────────────────────────────────────
// All colors are OPAQUE — transparency is applied at the Layer level.
// This prevents opacity stacking when strokes overlap.

const LAYER_OPACITY = 0.5;                      // overall mask layer transparency
const MIN_BRUSH = 4;
const MAX_BRUSH = 120;

const drawMaskShape = (ctx: CanvasRenderingContext2D, s: DrawnShape) => {
    if (s.type === 'line' && s.tool === 'eraser') {
        ctx.globalCompositeOperation = 'source-over';
        ctx.strokeStyle = '#fff';
        ctx.fillStyle = '#fff';
        ctx.lineWidth = s.strokeWidth;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        if (s.points.length >= 4) {
            ctx.moveTo(s.points[0], s.points[1]);
            for (let i = 2; i < s.points.length; i += 2) ctx.lineTo(s.points[i], s.points[i + 1]);
            ctx.stroke();
        } else if (s.points.length >= 2) {
            ctx.arc(s.points[0], s.points[1], s.strokeWidth / 2, 0, Math.PI * 2);
            ctx.fill();
        }
        return;
    }

    ctx.globalCompositeOperation = 'destination-out';
    if (s.type === 'line') {
        if (s.closed && s.points.length >= 6) {
            ctx.beginPath();
            ctx.moveTo(s.points[0], s.points[1]);
            for (let i = 2; i < s.points.length; i += 2) ctx.lineTo(s.points[i], s.points[i + 1]);
            ctx.closePath();
            ctx.fill();
        } else {
            ctx.lineWidth = s.strokeWidth;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.beginPath();
            if (s.points.length >= 4) {
                ctx.moveTo(s.points[0], s.points[1]);
                for (let i = 2; i < s.points.length; i += 2) ctx.lineTo(s.points[i], s.points[i + 1]);
                ctx.stroke();
            } else if (s.points.length >= 2) {
                ctx.arc(s.points[0], s.points[1], s.strokeWidth / 2, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    } else if (s.type === 'rect') {
        ctx.fillRect(s.x, s.y, s.width, s.height);
    } else if (s.type === 'ellipse') {
        ctx.beginPath();
        ctx.ellipse(s.x, s.y, s.radiusX, s.radiusY, 0, 0, Math.PI * 2);
        ctx.fill();
    }
};

const renderMaskCanvas = (
    width: number,
    height: number,
    existingMaskImg: HTMLImageElement | null,
    shapes: DrawnShape[],
) => {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d')!;

    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, width, height);

    if (existingMaskImg) {
        ctx.globalCompositeOperation = 'destination-in';
        ctx.drawImage(existingMaskImg, 0, 0, width, height);
        ctx.globalCompositeOperation = 'source-over';
    }

    for (const shape of shapes) drawMaskShape(ctx, shape);
    ctx.globalCompositeOperation = 'source-over';
    return canvas;
};

const renderMaskPreviewCanvas = (maskCanvas: HTMLCanvasElement) => {
    const canvas = document.createElement('canvas');
    canvas.width = maskCanvas.width;
    canvas.height = maskCanvas.height;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(maskCanvas, 0, 0);

    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = img.data;
    for (let i = 0; i < data.length; i += 4) {
        const maskedAmount = 255 - data[i + 3];
        data[i] = 100;
        data[i + 1] = 180;
        data[i + 2] = 255;
        data[i + 3] = Math.round(maskedAmount * LAYER_OPACITY);
    }
    ctx.putImageData(img, 0, 0);
    return canvas;
};

function LiveDrawingShape({ shape }: { shape: DrawnShape | null }) {
    if (!shape) return null;

    const maskFill = 'rgba(100,180,255,0.45)';
    const maskStroke = 'rgba(100,180,255,0.75)';
    const eraserStroke = 'rgba(255,255,255,0.72)';

    if (shape.type === 'line') {
        const isEraser = shape.tool === 'eraser';
        return (
            <Line
                points={shape.points}
                closed={shape.closed}
                fill={shape.closed && !isEraser ? maskFill : undefined}
                stroke={isEraser ? eraserStroke : maskStroke}
                strokeWidth={shape.strokeWidth}
                lineCap="round"
                lineJoin="round"
                listening={false}
            />
        );
    }

    if (shape.type === 'rect') {
        return (
            <Rect
                x={shape.x}
                y={shape.y}
                width={shape.width}
                height={shape.height}
                fill={maskFill}
                stroke={maskStroke}
                strokeWidth={2}
                listening={false}
            />
        );
    }

    return (
        <Ellipse
            x={shape.x}
            y={shape.y}
            radiusX={shape.radiusX}
            radiusY={shape.radiusY}
            fill={maskFill}
            stroke={maskStroke}
            strokeWidth={2}
            listening={false}
        />
    );
}

// ── Component ──────────────────────────────────────────────────

export function MaskEditor({ imageSrc, existingMask, existingFeather, onConfirm, onCancel }: MaskEditorProps) {
    const [tool, setTool] = useState<ToolType>('brush');
    const [brushSize, setBrushSize] = useState(30);
    const [feather, setFeather] = useState(existingFeather ?? 0);
    const [outputScale, setOutputScale] = useState(100);

    // Committed shapes (undo-able) vs currently-drawing shape (live preview)
    const [shapes, setShapes] = useState<DrawnShape[]>([]);
    const [undoneShapes, setUndoneShapes] = useState<DrawnShape[]>([]);
    const [drawingShape, setDrawingShape] = useState<DrawnShape | null>(null);
    const isDrawing = useRef(false);
    const drawStart = useRef<{ x: number; y: number } | null>(null);

    // Refs that mirror state — lets handlers stay stable (no recreate on every frame)
    const toolRef = useRef(tool);
    const brushSizeRef = useRef(brushSize);
    toolRef.current = tool;
    brushSizeRef.current = brushSize;

    // Image
    const [image, setImage] = useState<HTMLImageElement | null>(null);
    const [existingMaskImg, setExistingMaskImg] = useState<HTMLImageElement | null>(null);
    const [stageSize, setStageSize] = useState({ width: 800, height: 600 });
    const [scale, setScale] = useState(1);
    const [offset, setOffset] = useState({ x: 0, y: 0 });

    const stageRef = useRef<Konva.Stage>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // Stable coord helper via ref
    const scaleRef = useRef(scale);
    const offsetRef = useRef(offset);
    scaleRef.current = scale;
    offsetRef.current = offset;

    // Load images
    useEffect(() => {
        const img = new window.Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => setImage(img);
        img.src = imageSrc;
    }, [imageSrc]);

    useEffect(() => {
        if (!existingMask) return;
        const img = new window.Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => setExistingMaskImg(img);
        img.src = existingMask;
    }, [existingMask]);

    // Fit image in container
    useEffect(() => {
        if (!image || !containerRef.current) return;
        const update = () => {
            const c = containerRef.current!;
            const cw = c.clientWidth, ch = c.clientHeight;
            const iw = image.naturalWidth, ih = image.naturalHeight;
            const s = Math.min((cw - 40) / iw, (ch - 40) / ih, 1);
            setScale(s);
            setStageSize({ width: cw, height: ch });
            setOffset({ x: (cw - iw * s) / 2, y: (ch - ih * s) / 2 });
        };
        update();
        const ro = new ResizeObserver(update);
        ro.observe(containerRef.current);
        return () => ro.disconnect();
    }, [image]);

    // Stable getPos — reads from refs, never triggers re-render
    const getPos = useCallback(() => {
        const p = stageRef.current?.getPointerPosition();
        if (!p) return null;
        return {
            x: (p.x - offsetRef.current.x) / scaleRef.current,
            y: (p.y - offsetRef.current.y) / scaleRef.current,
        };
    }, []);   // empty deps — stable forever

    // ── Drawing handlers — all stable (zero state deps) ──
    const onDown = useCallback(() => {
        const pos = getPos();
        if (!pos) return;
        isDrawing.current = true;
        drawStart.current = pos;
        setUndoneShapes([]);

        const t = toolRef.current;
        if (t === 'brush' || t === 'eraser' || t === 'lasso') {
            setDrawingShape({
                type: 'line', tool: t === 'lasso' ? 'lasso' : t,
                // Duplicate the initial point so a single click renders a dot (zero-length line with round cap)
                points: [pos.x, pos.y, pos.x, pos.y], strokeWidth: brushSizeRef.current,
                closed: t === 'lasso',
            });
        }
    }, [getPos]);

    const onMove = useCallback(() => {
        if (!isDrawing.current) return;
        const pos = getPos();
        if (!pos) return;

        const t = toolRef.current;
        if (t === 'brush' || t === 'eraser' || t === 'lasso') {
            setDrawingShape(prev => {
                if (!prev || prev.type !== 'line') return prev;
                return { ...prev, points: [...prev.points, pos.x, pos.y] };
            });
        } else if (t === 'rect' && drawStart.current) {
            const s = drawStart.current;
            setDrawingShape({
                type: 'rect',
                x: Math.min(s.x, pos.x), y: Math.min(s.y, pos.y),
                width: Math.abs(pos.x - s.x), height: Math.abs(pos.y - s.y),
            });
        } else if (t === 'ellipse' && drawStart.current) {
            const s = drawStart.current;
            setDrawingShape({
                type: 'ellipse',
                x: (s.x + pos.x) / 2, y: (s.y + pos.y) / 2,
                radiusX: Math.abs(pos.x - s.x) / 2, radiusY: Math.abs(pos.y - s.y) / 2,
            });
        }
    }, [getPos]);   // stable — no drawingShape/tool dependency

    const onUp = useCallback(() => {
        if (!isDrawing.current) return;
        isDrawing.current = false;

        setDrawingShape(prev => {
            if (!prev) return null;
            // Commit to history
            const final = { ...prev };
            if (final.type === 'line' && final.tool === 'lasso') {
                final.closed = true;
            }
            setShapes(s => [...s, final]);
            return null;  // clear drawing shape
        });
        drawStart.current = null;
    }, []);   // stable — reads from setDrawingShape(prev)

    // ── Undo / Redo ──
    const undo = useCallback(() => {
        setShapes(prev => {
            if (!prev.length) return prev;
            setUndoneShapes(u => [prev[prev.length - 1], ...u]);
            return prev.slice(0, -1);
        });
    }, []);
    const redo = useCallback(() => {
        setUndoneShapes(prev => {
            if (!prev.length) return prev;
            setShapes(s => [...s, prev[0]]);
            return prev.slice(1);
        });
    }, []);
    const resetAll = useCallback(() => {
        setShapes([]); setUndoneShapes([]); setExistingMaskImg(null);
    }, []);

    // Keyboard shortcuts
    useEffect(() => {
        const h = (e: KeyboardEvent) => {
            if (e.ctrlKey && e.key === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
            else if (e.ctrlKey && e.key === 'y') { e.preventDefault(); redo(); }
            else if (e.key === 'Escape') onCancel();
        };
        window.addEventListener('keydown', h);
        return () => window.removeEventListener('keydown', h);
    }, [undo, redo, onCancel]);

    // ── Export mask ──
    const handleConfirm = useCallback(() => {
        if (!image) return;
        const iw = image.naturalWidth, ih = image.naturalHeight;
        const c = renderMaskCanvas(iw, ih, existingMaskImg, shapes);
        const dataUrl = c.toDataURL('image/png');
        
        // Debug: uncomment to download mask for visual inspection
        // const a = document.createElement('a');
        // a.href = dataUrl;
        // a.download = 'mask_debug.png';
        // a.click();
        // console.log("%c🖌️ 遮罩已生成! 并已触发自动下载 (mask_debug.png)，你可以在本地打开查看真实 PNG。", "color: #f43f5e; font-weight: bold; font-size: 14px;");

        const outW = Math.max(16, Math.round(iw * (outputScale / 100) / 16) * 16);
        const outH = Math.max(16, Math.round(ih * (outputScale / 100) / 16) * 16);
        const maxEdge = Math.max(outW, outH);
        onConfirm(dataUrl, feather, maxEdge.toString());
    }, [image, shapes, existingMaskImg, feather, outputScale, onConfirm]);

    const maskPreviewCanvas = useMemo(() => {
        if (!image) return null;
        const maskCanvas = renderMaskCanvas(
            image.naturalWidth,
            image.naturalHeight,
            existingMaskImg,
            shapes,
        );
        return renderMaskPreviewCanvas(maskCanvas);
    }, [image, existingMaskImg, shapes]);

    // ── Cursor ──
    const cursor = useMemo(() => {
        if (tool === 'brush' || tool === 'eraser' || tool === 'lasso') {
            const sz = Math.max(6, brushSize * scale);
            const h = sz / 2;
            const clr = tool === 'eraser' ? 'rgba(255,100,100,0.7)' : 'rgba(100,180,255,0.7)';
            const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${sz}' height='${sz}'><circle cx='${h}' cy='${h}' r='${h - 1}' fill='none' stroke='${clr}' stroke-width='2'/></svg>`;
            return `url("data:image/svg+xml,${encodeURIComponent(svg)}") ${h} ${h}, crosshair`;
        }
        return 'crosshair';
    }, [tool, brushSize, scale]);

    // ── Render shape helper ──
    // All shapes use OPAQUE colors. Transparency comes from the Layer.
    // Eraser uses destination-out with opaque white to fully cut out areas.
    const tools: { id: ToolType; icon: typeof Paintbrush; label: string }[] = [
        { id: 'brush', icon: Paintbrush, label: '画笔' },
        { id: 'lasso', icon: Lasso, label: '套索' },
        { id: 'rect', icon: Square, label: '矩形' },
        { id: 'ellipse', icon: Circle, label: '椭圆' },
        { id: 'eraser', icon: Eraser, label: '橡皮擦' },
    ];

    const hasMask = shapes.length > 0 || !!existingMaskImg;

    return (
        <div className="fixed inset-0 z-[100] flex flex-col bg-zinc-900/30 backdrop-blur-xl transition-all duration-300">
            {/* Top Navigation Bar */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-zinc-900/50 backdrop-blur-md relative z-10 shadow-lg">
                <div className="flex items-center gap-4">
                    <div className="p-2 bg-rose-500/10 rounded-xl">
                        <Paintbrush className="w-5 h-5 text-rose-500" />
                    </div>
                    <div>
                        <h2 className="text-sm font-semibold text-zinc-100 tracking-wide">局部重绘遮罩</h2>
                        <span className="text-xs text-zinc-500">绘制需要 AI 重新生成的区域</span>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <button onClick={onCancel}
                        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-zinc-800/50 text-zinc-300 hover:bg-zinc-800 hover:text-white transition-all text-sm font-medium border border-white/5">
                        <X className="w-4 h-4" /> 取消
                    </button>
                    <button onClick={handleConfirm} disabled={!hasMask}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all shadow-lg ${
                            hasMask 
                                ? 'bg-gradient-to-r from-rose-500 to-pink-600 text-white hover:shadow-rose-500/25 hover:scale-[1.02]' 
                                : 'bg-zinc-800/30 text-zinc-600 border border-white/5 cursor-not-allowed'
                        }`}>
                        <Check className="w-4 h-4" /> 确认遮罩
                    </button>
                </div>
            </div>

            <div className="flex-1 relative overflow-hidden flex items-center justify-center">
                {/* Floating Toolbar Panel */}
                <div className="absolute left-6 top-1/2 -translate-y-1/2 z-20 w-[240px] flex flex-col gap-6 p-5 rounded-2xl bg-zinc-900/80 backdrop-blur-2xl border border-white/10 shadow-2xl">
                    
                    {/* Tool Selection */}
                    <div className="space-y-3">
                        <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-semibold px-1">绘图工具</span>
                        <div className="grid grid-cols-5 gap-1.5 p-1.5 bg-zinc-950/50 rounded-xl border border-white/5">
                            {tools.map(t => {
                                const Icon = t.icon;
                                const isActive = tool === t.id;
                                return (
                                    <button key={t.id} onClick={() => setTool(t.id)}
                                        className={`flex flex-col items-center justify-center p-2 rounded-lg transition-all duration-200 ${
                                            isActive 
                                                ? 'bg-zinc-800 text-rose-400 shadow-sm' 
                                                : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
                                        }`}
                                        title={t.label}>
                                        <Icon className="w-[18px] h-[18px]" strokeWidth={isActive ? 2.5 : 2} />
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Sliders */}
                    <div className="space-y-5">
                        {(tool === 'brush' || tool === 'eraser') && (
                            <div className="space-y-2">
                                <div className="flex justify-between items-center px-1">
                                    <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-semibold">笔刷大小</span>
                                    <span className="text-xs text-zinc-300 font-medium bg-zinc-800 px-2 py-0.5 rounded-md">{brushSize}px</span>
                                </div>
                                <input type="range" min={MIN_BRUSH} max={MAX_BRUSH} value={brushSize}
                                    onChange={e => setBrushSize(+e.target.value)} 
                                    className="w-full h-1.5 bg-zinc-800 rounded-full appearance-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-rose-500 [&::-webkit-slider-thumb]:rounded-full cursor-pointer hover:[&::-webkit-slider-thumb]:bg-rose-400 transition-all" />
                            </div>
                        )}

                        <div className="space-y-2">
                            <div className="flex justify-between items-center px-1">
                                <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-semibold">边缘羽化</span>
                                <span className="text-xs text-zinc-300 font-medium bg-zinc-800 px-2 py-0.5 rounded-md">{feather}px</span>
                            </div>
                            <input type="range" min={0} max={60} value={feather}
                                onChange={e => setFeather(+e.target.value)} 
                                className="w-full h-1.5 bg-zinc-800 rounded-full appearance-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-rose-500 [&::-webkit-slider-thumb]:rounded-full cursor-pointer hover:[&::-webkit-slider-thumb]:bg-rose-400 transition-all" />
                            <div className="flex justify-between px-1 text-[9px] text-zinc-600 font-medium">
                                <span>硬边缘</span>
                                <span>柔和过渡</span>
                            </div>
                        </div>

                        <div className="space-y-2">
                            <div className="flex justify-between items-center px-1">
                                <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-semibold">输入图缩放</span>
                                <span className="text-xs text-zinc-300 font-medium bg-zinc-800 px-2 py-0.5 rounded-md">
                                    {image ? `${Math.max(16, Math.round(image.naturalWidth * (outputScale / 100) / 16) * 16)}x${Math.max(16, Math.round(image.naturalHeight * (outputScale / 100) / 16) * 16)}` : `${outputScale}%`}
                                </span>
                            </div>
                            <input type="range" min={10} max={100} step={5} value={outputScale}
                                onChange={e => setOutputScale(+e.target.value)} 
                                className="w-full h-1.5 bg-zinc-800 rounded-full appearance-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:bg-blue-500 [&::-webkit-slider-thumb]:rounded-full cursor-pointer hover:[&::-webkit-slider-thumb]:bg-blue-400 transition-all" />
                            <div className="flex justify-between px-1 text-[9px] text-zinc-600 font-medium">
                                <span>10% (小尺寸)</span>
                                <span>100% (原图)</span>
                            </div>
                        </div>
                    </div>

                    <div className="h-px bg-gradient-to-r from-transparent via-white/10 to-transparent my-1"></div>

                    {/* History Actions */}
                    <div className="grid grid-cols-3 gap-2">
                        <button onClick={undo} disabled={!shapes.length}
                            className="flex flex-col items-center gap-1.5 p-2 rounded-xl text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80 disabled:opacity-30 disabled:hover:bg-transparent transition-all" title="Ctrl+Z">
                            <Undo2 className="w-4 h-4" />
                            <span className="text-[10px] font-medium">撤销</span>
                        </button>
                        <button onClick={redo} disabled={!undoneShapes.length}
                            className="flex flex-col items-center gap-1.5 p-2 rounded-xl text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/80 disabled:opacity-30 disabled:hover:bg-transparent transition-all" title="Ctrl+Y">
                            <Redo2 className="w-4 h-4" />
                            <span className="text-[10px] font-medium">重做</span>
                        </button>
                        <button onClick={resetAll} disabled={!hasMask}
                            className="flex flex-col items-center gap-1.5 p-2 rounded-xl text-zinc-400 hover:text-rose-400 hover:bg-rose-500/10 disabled:opacity-30 disabled:hover:bg-transparent transition-all">
                            <RotateCcw className="w-4 h-4" />
                            <span className="text-[10px] font-medium">重置</span>
                        </button>
                    </div>
                </div>

                {/* Canvas Container */}
                <div ref={containerRef} className="absolute inset-0 bg-zinc-950/50" style={{ cursor }}>
                    {/* Centered subtle crosshair pattern for canvas background */}
                    <div className="absolute inset-0 opacity-[0.03] pointer-events-none" 
                         style={{ backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)', backgroundSize: '32px 32px' }} />
                    
                    {image && (
                        <Stage ref={stageRef} width={stageSize.width} height={stageSize.height}
                            onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp}
                            onTouchStart={onDown} onTouchMove={onMove} onTouchEnd={onUp}
                            className="relative z-10">
                            <Layer>
                                {/* Draw a subtle border around the image area */}
                                <Rect x={offset.x - 1} y={offset.y - 1} width={image.naturalWidth * scale + 2} height={image.naturalHeight * scale + 2} stroke="rgba(255,255,255,0.1)" strokeWidth={1} listening={false} />
                                <KonvaImage image={image} x={offset.x} y={offset.y}
                                    width={image.naturalWidth * scale} height={image.naturalHeight * scale} listening={false} />
                            </Layer>
                            <Layer x={offset.x} y={offset.y} scaleX={scale} scaleY={scale}
                                clipX={0} clipY={0} clipWidth={image.naturalWidth} clipHeight={image.naturalHeight}>
                                {maskPreviewCanvas && (
                                    <KonvaImage image={maskPreviewCanvas}
                                        width={image.naturalWidth} height={image.naturalHeight}
                                        listening={false} />
                                )}
                                <LiveDrawingShape shape={drawingShape} />
                            </Layer>
                        </Stage>
                    )}
                </div>
            </div>
        </div>
    );
}
