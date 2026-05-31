import { Search, Calendar, Star, Tag, ChevronRight, ChevronDown, ImagePlus } from 'lucide-react';
import { AnimatePresence } from 'framer-motion';
import { useStore } from '../../store';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { useState, useMemo, useCallback } from 'react';
import type { ImageItem } from '../../types';
import { SettingsPanel } from '../features/SettingsPanel';
import { ImportGalleryModal } from '../features/ImportGalleryModal';

// ─── Types for grouped date structure ───────────────────────────
interface DayEntry {
    day: string;    // 'dd'
    dateStr: string; // 'yyyy-MM-dd' (for creating Date object)
    count: number;
}

interface MonthGroup {
    month: string;  // 'MM'
    label: string;  // '2月'
    count: number;
    days: DayEntry[];
}

interface YearGroup {
    year: string;   // 'yyyy'
    label: string;  // '2026年'
    count: number;
    months: MonthGroup[];
}

// ─── Helper: build grouped date structure from images ───────────
function buildGroupedDates(images: ImageItem[]): YearGroup[] {
    const yearMap = new Map<string, Map<string, Map<string, number>>>();

    images.forEach((img) => {
        const d = new Date(img.createdAt);
        const yyyy = format(d, 'yyyy');
        const mm = format(d, 'MM');
        const dd = format(d, 'dd');

        if (!yearMap.has(yyyy)) yearMap.set(yyyy, new Map());
        const monthMap = yearMap.get(yyyy)!;
        if (!monthMap.has(mm)) monthMap.set(mm, new Map());
        const dayMap = monthMap.get(mm)!;
        dayMap.set(dd, (dayMap.get(dd) || 0) + 1);
    });

    const years: YearGroup[] = [];
    // Sort years descending
    for (const yyyy of [...yearMap.keys()].sort().reverse()) {
        const monthMap = yearMap.get(yyyy)!;
        let yearCount = 0;
        const months: MonthGroup[] = [];

        // Sort months descending
        for (const mm of [...monthMap.keys()].sort().reverse()) {
            const dayMap = monthMap.get(mm)!;
            let monthCount = 0;
            const days: DayEntry[] = [];

            // Sort days descending
            for (const dd of [...dayMap.keys()].sort().reverse()) {
                const count = dayMap.get(dd)!;
                days.push({ day: dd, dateStr: `${yyyy}-${mm}-${dd}`, count });
                monthCount += count;
            }

            months.push({
                month: mm,
                label: `${parseInt(mm)}月`,
                count: monthCount,
                days,
            });
            yearCount += monthCount;
        }

        years.push({
            year: yyyy,
            label: `${yyyy}年`,
            count: yearCount,
            months,
        });
    }

    return years;
}

// ─── DatePickerDropdown sub-component ───────────────────────────
function DatePickerDropdown({
    groupedDates,
    selectedDate,
    onSelectDate,
    onClear,
}: {
    groupedDates: YearGroup[];
    selectedDate: Date | null;
    onSelectDate: (dateStr: string) => void;
    onClear: () => void;
}) {
    // Default: expand the most recent year and its most recent month
    const defaultYear = groupedDates[0]?.year ?? '';
    const defaultMonth = groupedDates[0]?.months[0]
        ? `${defaultYear}-${groupedDates[0].months[0].month}`
        : '';

    const [expandedYears, setExpandedYears] = useState<Set<string>>(
        () => new Set(defaultYear ? [defaultYear] : [])
    );
    const [expandedMonths, setExpandedMonths] = useState<Set<string>>(
        () => new Set(defaultMonth ? [defaultMonth] : [])
    );

    const toggleYear = useCallback((year: string) => {
        setExpandedYears((prev) => {
            const next = new Set(prev);
            if (next.has(year)) next.delete(year);
            else next.add(year);
            return next;
        });
    }, []);

    const toggleMonth = useCallback((key: string) => {
        setExpandedMonths((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    }, []);

    const selectedDateStr = selectedDate ? format(selectedDate, 'yyyy-MM-dd') : '';

    return (
        <div className="absolute left-1/2 top-full mt-2 min-w-[210px] max-h-[26rem] -translate-x-1/2 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-popover)] p-2 shadow-[var(--shadow-card)] backdrop-blur-xl animate-fade-in">
            {/* Clear filter */}
            <button
                onClick={onClear}
                className="mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]"
            >
                <span>全部日期</span>
                {selectedDate && (
                    <span className="rounded-full bg-[var(--accent-primary)]/15 px-2 py-0.5 text-xs text-[var(--accent-primary)]">
                        已筛选
                    </span>
                )}
            </button>
            <div className="my-1 h-px bg-[var(--border-subtle)]" />

            {groupedDates.map((yearGroup) => {
                const yearExpanded = expandedYears.has(yearGroup.year);
                return (
                    <div key={yearGroup.year}>
                        {/* Year row */}
                        <button
                            onClick={() => toggleYear(yearGroup.year)}
                            className="mt-1 flex w-full items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-card-hover)]"
                        >
                            {yearExpanded
                                ? <ChevronDown className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                                : <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />}
                            <span className="flex-1 text-left">{yearGroup.label}</span>
                            <span className="text-xs text-[var(--text-muted)] tabular-nums">
                                {yearGroup.count}
                            </span>
                        </button>

                        {/* Months */}
                        {yearExpanded && yearGroup.months.map((monthGroup) => {
                            const monthKey = `${yearGroup.year}-${monthGroup.month}`;
                            const monthExpanded = expandedMonths.has(monthKey);
                            return (
                                <div key={monthKey}>
                                    {/* Month row */}
                                    <button
                                        onClick={() => toggleMonth(monthKey)}
                                        className="flex w-full items-center gap-1.5 rounded-xl py-1.5 pl-7 pr-3 text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]"
                                    >
                                        {monthExpanded
                                            ? <ChevronDown className="w-3 h-3 text-[var(--text-muted)] shrink-0" />
                                            : <ChevronRight className="w-3 h-3 text-[var(--text-muted)] shrink-0" />}
                                        <span className="flex-1 text-left">{monthGroup.label}</span>
                                        <span className="text-xs text-[var(--text-muted)] tabular-nums">
                                            {monthGroup.count}
                                        </span>
                                    </button>

                                    {/* Days */}
                                    {monthExpanded && monthGroup.days.map((dayEntry) => {
                                        const isSelected = dayEntry.dateStr === selectedDateStr;
                                        return (
                                            <button
                                                key={dayEntry.dateStr}
                                                onClick={() => onSelectDate(dayEntry.dateStr)}
                                                className={`flex w-full items-center gap-1.5 rounded-xl py-1.5 pl-14 pr-3 text-sm transition-all ${isSelected
                                                    ? 'bg-[var(--accent-primary)]/16 text-[var(--accent-primary)] shadow-[inset_0_0_0_1px_rgba(244,63,94,0.22)]'
                                                    : 'text-[var(--text-primary)] hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]'
                                                    }`}
                                            >
                                                <span className="flex-1 text-left">{parseInt(dayEntry.day)}日</span>
                                                <span className="text-xs text-[var(--text-muted)] tabular-nums">
                                                    {dayEntry.count}
                                                </span>
                                            </button>
                                        );
                                    })}
                                </div>
                            );
                        })}
                    </div>
                );
            })}
        </div>
    );
}

// ─── TopNav main component ──────────────────────────────────────
export function TopNav() {
    const filters = useStore((s) => s.filters);
    const setSearchQuery = useStore((s) => s.setSearchQuery);
    const setSelectedDate = useStore((s) => s.setSelectedDate);
    const setSelectedTags = useStore((s) => s.setSelectedTags);
    const toggleFavoritesOnly = useStore((s) => s.toggleFavoritesOnly);
    const allTags = useStore((s) => s.allTags);
    const images = useStore((s) => s.images);
    const backendCapabilities = useStore((s) => s.backendCapabilities);

    const [showCalendar, setShowCalendar] = useState(false);
    const [showTagFilter, setShowTagFilter] = useState(false);
    const [showImportModal, setShowImportModal] = useState(false);
    const [showImportHint, setShowImportHint] = useState(false);

    // Build grouped date structure
    const groupedDates = useMemo(() => buildGroupedDates(images), [images]);

    const handleSelectDate = useCallback((dateStr: string) => {
        setSelectedDate(new Date(dateStr));
        setShowCalendar(false);
    }, [setSelectedDate]);

    const handleClearDate = useCallback(() => {
        setSelectedDate(null);
        setShowCalendar(false);
    }, [setSelectedDate]);

    return (
        <nav className="sticky top-0 z-40 border-b border-[var(--border-subtle)] bg-[var(--bg-nav)] backdrop-blur-xl">
            <div className="mx-auto max-w-[1800px] px-4 py-3 md:px-6">
                <div className="flex items-center gap-3">
                    {/* Search */}
                    <div className="relative min-w-0 flex-1 md:max-w-xl">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
                        <input
                            type="text"
                            placeholder="搜索 Prompt..."
                            value={filters.searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-10 pr-4 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-primary)] transition-colors"
                        />
                    </div>

                    {/* Date Filter */}
                    <div className="relative">
                        <button
                            onClick={() => setShowCalendar(!showCalendar)}
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${filters.selectedDate
                                ? 'bg-[var(--accent-primary)]/20 border-[var(--accent-primary)] text-[var(--accent-primary)]'
                                : 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]'
                                }`}
                        >
                            <Calendar className="w-4 h-4" />
                            <span className="text-sm">
                                {filters.selectedDate
                                    ? format(filters.selectedDate, 'M月d日', { locale: zhCN })
                                    : '日期'}
                            </span>
                        </button>

                        {showCalendar && (
                            <DatePickerDropdown
                                groupedDates={groupedDates}
                                selectedDate={filters.selectedDate}
                                onSelectDate={handleSelectDate}
                                onClear={handleClearDate}
                            />
                        )}
                    </div>

                    {/* Tags Filter */}
                    <div className="relative">
                        <button
                            onClick={() => setShowTagFilter(!showTagFilter)}
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${filters.selectedTags.length > 0
                                ? 'bg-[var(--accent-primary)]/20 border-[var(--accent-primary)] text-[var(--accent-primary)]'
                                : 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]'
                                }`}
                        >
                            <Tag className="w-4 h-4" />
                            <span className="text-sm">
                                {filters.selectedTags.length > 0
                                    ? `${filters.selectedTags.length} 个标签`
                                    : '标签'}
                            </span>
                        </button>

                        {showTagFilter && allTags.length > 0 && (
                            <div className="absolute left-1/2 top-full mt-2 min-w-[190px] max-w-[260px] max-h-[26rem] -translate-x-1/2 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-popover)] p-2 shadow-[var(--shadow-card)] backdrop-blur-xl animate-fade-in">
                                <button
                                    onClick={() => {
                                        setSelectedTags([]);
                                        setShowTagFilter(false);
                                    }}
                                    className="mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]"
                                >
                                    <span>清除筛选</span>
                                    {filters.selectedTags.length > 0 && (
                                        <span className="rounded-full bg-[var(--accent-primary)]/15 px-2 py-0.5 text-xs text-[var(--accent-primary)]">
                                            {filters.selectedTags.length}
                                        </span>
                                    )}
                                </button>
                                <div className="my-1 h-px bg-[var(--border-subtle)]" />
                                {allTags.map((tag) => (
                                    <button
                                        key={tag}
                                        onClick={() => {
                                            const newTags = filters.selectedTags.includes(tag)
                                                ? filters.selectedTags.filter((t) => t !== tag)
                                                : [...filters.selectedTags, tag];
                                            setSelectedTags(newTags);
                                        }}
                                        className={`mt-1 flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition-all ${filters.selectedTags.includes(tag)
                                            ? 'bg-[var(--accent-primary)]/16 text-[var(--accent-primary)] shadow-[inset_0_0_0_1px_rgba(244,63,94,0.22)]'
                                            : 'text-[var(--text-primary)] hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]'
                                            }`}
                                    >
                                        <span className="truncate">{tag}</span>
                                        {filters.selectedTags.includes(tag) && (
                                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)] shadow-[0_0_10px_rgba(244,63,94,0.55)]" />
                                        )}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Favorites */}
                    <button
                        onClick={toggleFavoritesOnly}
                        className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${filters.showFavoritesOnly
                            ? 'bg-[var(--accent-primary)]/16 border-[var(--accent-primary)] text-[var(--accent-primary)]'
                            : 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--text-muted)]'
                            }`}
                    >
                        <Star className={`w-4 h-4 ${filters.showFavoritesOnly ? 'fill-current' : ''}`} />
                        <span className="text-sm">收藏</span>
                    </button>

                    {/* Import */}
                    <div className="relative">
                        <button
                            onClick={() => {
                                if (backendCapabilities.features.galleryImport) {
                                    setShowImportModal(true);
                                    return;
                                }
                                setShowImportHint((value) => !value);
                            }}
                            className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors ${
                                backendCapabilities.features.galleryImport
                                    ? 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)]'
                                    : 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-muted)] opacity-70'
                            }`}
                            title={backendCapabilities.features.galleryImport ? '导入到画廊' : '当前后端不支持导入'}
                        >
                            <ImagePlus className="w-4 h-4" />
                            <span className="text-sm">本地导入</span>
                        </button>
                        {showImportHint && !backendCapabilities.features.galleryImport && (
                            <div className="absolute left-1/2 top-full mt-2 w-56 -translate-x-1/2 rounded-lg glass p-3 text-sm text-[var(--text-secondary)] shadow-lg animate-fade-in">
                                当前后端不支持产品内导入。
                            </div>
                        )}
                    </div>

                    {/* Settings */}
                    <SettingsPanel />
                </div>
            </div>

            <AnimatePresence>
                {showImportModal && backendCapabilities.features.galleryImport && (
                    <ImportGalleryModal onClose={() => setShowImportModal(false)} />
                )}
            </AnimatePresence>
        </nav>
    );
}
