import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  Clock,
  Copy,
  ExternalLink,
  FolderOpen,
  HardDrive,
  History,
  Loader2,
  Package,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
} from 'lucide-react';
import type { PackageCandidateItem, PackageSlotState } from '../types';

interface PackagePanelProps {
  folder: string;
  recentDirs: string[];
  scanning: boolean;
  packages: Record<string, PackageSlotState>;
  onChooseFolder: () => void;
  onScanFolder: (folder: string) => void;
  onOpenFolder: (folder: string) => void;
  onSelectPackage: (kind: string, index: number, revision?: number) => void;
  onCopyText: (text: string, label: string) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function formatRelativeTime(mtimeMs: number): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - mtimeMs) / 1000));
  if (diffSec < 60) return '刚刚';
  const min = Math.floor(diffSec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(mtimeMs).toLocaleDateString('zh-CN');
}

export function PackagePanel({
  folder,
  recentDirs,
  scanning,
  packages,
  onChooseFolder,
  onScanFolder,
  onOpenFolder,
  onSelectPackage,
  onCopyText,
}: PackagePanelProps) {
  const [folderInput, setFolderInput] = useState(folder);
  const [recentOpen, setRecentOpen] = useState(false);
  const recentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setFolderInput(folder);
  }, [folder]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (recentRef.current && !recentRef.current.contains(e.target as Node)) {
        setRecentOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const apkSlot = packages.APK ?? { kind: 'APK', selectedIndex: -1, allowTest: null, candidates: [] };
  const hapSlot = packages.HAP ?? { kind: 'HAP', selectedIndex: -1, allowTest: null, candidates: [] };

  return (
    <section className="flex flex-col rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-card)] shadow-xs">
      {/* Directory bar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-hairline)] px-3 py-2">
        <div className="flex items-center gap-1.5 mr-0.5">
          <Package className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-[12.5px] font-semibold text-[var(--ink-primary)]">安装包</h2>
        </div>

        <div className="relative flex min-w-[160px] flex-1 items-center">
          <input
            value={folderInput}
            onChange={(e) => setFolderInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onScanFolder(folderInput);
            }}
            placeholder="输入安装包目录后按 Enter，或直接将 .apk / .hap 拖入窗口…"
            className="font-mono-code h-7.5 w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] pl-2.5 pr-8 text-[11.5px] text-[var(--ink-primary)] placeholder:font-sans placeholder:text-[var(--ink-muted)] focus:border-blue-500 focus:bg-[var(--surface-card)] focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
          {recentDirs.length > 0 && (
            <div className="absolute right-1" ref={recentRef}>
              <button
                type="button"
                onClick={() => setRecentOpen((v) => !v)}
                title="最近使用的目录"
                className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--ink-muted)] hover:bg-slate-200/70 hover:text-[var(--ink-primary)] dark:hover:bg-slate-700/60 cursor-pointer"
              >
                <History className="h-3.5 w-3.5" />
              </button>
              {recentOpen && (
                <div className="absolute right-0 z-30 mt-1.5 w-80 max-w-[75vw] overflow-hidden rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-card)] p-1 shadow-lg shadow-slate-900/10 dark:shadow-black/40">
                  <div className="px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
                    最近目录
                  </div>
                  {recentDirs.map((dir) => (
                    <button
                      key={dir}
                      type="button"
                      onClick={() => {
                        setRecentOpen(false);
                        setFolderInput(dir);
                        onScanFolder(dir);
                      }}
                      className="font-mono-code flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[11.5px] text-[var(--ink-primary)] transition-colors hover:bg-[var(--surface-subtle)] cursor-pointer"
                    >
                      <FolderOpen className="h-3.5 w-3.5 shrink-0 text-[var(--ink-muted)]" />
                      <span className="truncate">{dir}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onChooseFolder}
            className="flex h-7.5 items-center gap-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] px-2.5 text-[11.5px] font-medium text-[var(--ink-primary)] transition-colors hover:bg-slate-200/70 dark:hover:bg-slate-700/50 cursor-pointer"
          >
            <FolderOpen className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
            <span>选择目录</span>
          </button>

          <button
            type="button"
            disabled={scanning || !folderInput.trim()}
            onClick={() => onScanFolder(folderInput)}
            title="扫描当前目录中的最新 APK/HAP"
            className="flex h-7.5 items-center gap-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2.5 text-[11.5px] font-medium text-[var(--ink-primary)] transition-colors hover:bg-[var(--surface-subtle)] disabled:opacity-45 cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${scanning ? 'animate-spin text-blue-500' : ''}`} />
            <span>{scanning ? '扫描中' : '扫描'}</span>
          </button>

          {folder && (
            <button
              type="button"
              onClick={() => onOpenFolder(folder)}
              title="在资源管理器中打开目录"
              className="flex h-7.5 w-7.5 items-center justify-center rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] text-[var(--ink-secondary)] transition-colors hover:bg-[var(--surface-subtle)] hover:text-[var(--ink-primary)] cursor-pointer"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Dual APK / HAP Cards */}
      <div className="grid grid-cols-1 gap-2.5 p-2.5 sm:grid-cols-2">
        <PackageSlotCard
          slot={apkSlot}
          accent="emerald"
          platformTag="Android · APK"
          onSelect={(idx) => onSelectPackage('APK', idx, apkSlot.revision)}
          onCopyText={onCopyText}
        />
        <PackageSlotCard
          slot={hapSlot}
          accent="sky"
          platformTag="Harmony · HAP"
          onSelect={(idx) => onSelectPackage('HAP', idx, hapSlot.revision)}
          onCopyText={onCopyText}
        />
      </div>
    </section>
  );
}

interface PackageSlotCardProps {
  slot: PackageSlotState;
  accent: 'emerald' | 'sky';
  platformTag: string;
  onSelect: (index: number) => void;
  onCopyText: (text: string, label: string) => void;
}

function PackageSlotCard({
  slot,
  accent,
  platformTag,
  onSelect,
  onCopyText,
}: PackageSlotCardProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [search, setSearch] = useState('');
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const active: PackageCandidateItem | null =
    slot.selectedIndex >= 0 && slot.selectedIndex < slot.candidates.length
      ? slot.candidates[slot.selectedIndex]
      : null;

  const filteredCandidates = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return slot.candidates;
    return slot.candidates.filter(
      (c) =>
        c.filename.toLowerCase().includes(q) ||
        (c.appName ?? '').toLowerCase().includes(q) ||
        (c.packageName ?? '').toLowerCase().includes(q) ||
        c.versionText.toLowerCase().includes(q),
    );
  }, [slot.candidates, search]);

  const badgeClass =
    accent === 'emerald'
      ? 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
      : 'bg-sky-500/12 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300';

  const stripClass = accent === 'emerald' ? 'bg-emerald-500' : 'bg-sky-500';

  return (
    <div
      ref={popoverRef}
      className="relative flex flex-col justify-between rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-subtle)] p-2.5 transition-colors hover:border-slate-300 dark:hover:border-slate-600"
    >
      {/* Subtle left accent line */}
      <div className={`absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-r-full ${stripClass} opacity-80`} />

      {/* Top row: platform tag + candidate switcher */}
      <div className="flex items-center justify-between gap-2 pl-1.5">
        <div className="flex items-center gap-1.5">
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${badgeClass}`}>
            {platformTag}
          </span>
          {slot.kind === 'APK' && active && (
            <span
              title={
                slot.allowTest
                  ? '未明确为非 testOnly，将自动附加 adb install -t 保证可安装'
                  : '已识别 testOnly=false，将使用标准 adb install'
              }
              className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium ${
                slot.allowTest
                  ? 'bg-amber-500/12 text-amber-700 dark:text-amber-300'
                  : 'bg-slate-200/70 text-slate-600 dark:bg-slate-700/60 dark:text-slate-300'
              }`}
            >
              <ShieldCheck className="h-3 w-3" />
              {slot.allowTest ? '自动 -t' : '标准安装'}
            </span>
          )}
        </div>

        {slot.candidates.length > 0 && (
          <button
            type="button"
            onClick={() => {
              setSearch('');
              setPickerOpen((v) => !v);
            }}
            className="flex items-center gap-1 rounded-md border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1 text-[11px] font-medium text-[var(--ink-secondary)] transition-colors hover:text-[var(--ink-primary)] cursor-pointer"
          >
            <span>共 {slot.candidates.length} 个</span>
            <ChevronDown className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Body */}
      {!active ? (
        <div className="mt-2 flex items-center gap-2 pl-1.5 py-1.5 text-[11.5px] text-[var(--ink-muted)]">
          <Upload className="h-3.5 w-3.5 shrink-0 opacity-50" />
          <span>未找到 {slot.kind}，可选择目录或直接拖入文件</span>
        </div>
      ) : (
        <div className="mt-2 flex flex-col gap-1 pl-1.5">
          <div className="flex items-baseline justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-[13.5px] font-semibold text-[var(--ink-primary)]">
                {active.appName || active.filename}
              </span>
              {!active.labelLoaded && (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[var(--ink-muted)]" />
              )}
            </div>
            {active.versionText && (
              <span className="font-mono-code shrink-0 rounded-md bg-[var(--surface-card)] border border-[var(--border-hairline)] px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--ink-secondary)]">
                v{active.versionText}
              </span>
            )}
          </div>

          {/* Package name / Bundle name */}
          {active.packageName ? (
            <button
              type="button"
              onClick={() => onCopyText(active.packageName!, '包名')}
              title="点击复制包名 / bundleName"
              className="group/pkg flex w-fit max-w-full items-center gap-1.5 text-left text-[11.5px] text-[var(--ink-secondary)] hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer"
            >
              <span className="font-mono-code truncate">{active.packageName}</span>
              <Copy className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover/pkg:opacity-100" />
            </button>
          ) : active.statusHint && active.labelLoaded ? (
            <span className="text-[11px] text-amber-600 dark:text-amber-400">
              {active.statusHint}
            </span>
          ) : null}

          {/* File details row */}
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[10.5px] text-[var(--ink-muted)]">
            <span className="font-mono-code max-w-[200px] truncate" title={active.path}>
              {active.filename}
            </span>
            <span className="inline-flex items-center gap-1">
              <HardDrive className="h-3 w-3" />
              {formatBytes(active.sizeBytes)}
            </span>
            <span className="inline-flex items-center gap-1" title={new Date(active.mtimeMs).toLocaleString('zh-CN')}>
              <Clock className="h-3 w-3" />
              {formatRelativeTime(active.mtimeMs)}
            </span>
          </div>
        </div>
      )}

      {/* Searchable Candidate Switcher Popover */}
      {pickerOpen && slot.candidates.length > 0 && (
        <div className="absolute left-0 right-0 top-11 z-40 overflow-hidden rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-card)] shadow-xl shadow-slate-900/15 dark:shadow-black/50">
          {slot.candidates.length > 4 && (
            <div className="flex items-center gap-2 border-b border-[var(--border-hairline)] px-2.5 py-2">
              <Search className="h-3.5 w-3.5 text-[var(--ink-muted)]" />
              <input
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`搜索 ${slot.kind} 名称、版本号或文件名…`}
                className="w-full bg-transparent text-[12px] text-[var(--ink-primary)] placeholder:text-[var(--ink-muted)] outline-none"
              />
            </div>
          )}
          <div className="max-h-60 overflow-y-auto p-1">
            {filteredCandidates.length === 0 ? (
              <div className="py-5 text-center text-[12px] text-[var(--ink-muted)]">
                没有匹配的安装包
              </div>
            ) : (
              filteredCandidates.map((cand) => {
                const selected = cand.index === slot.selectedIndex;
                return (
                  <button
                    key={cand.path}
                    type="button"
                    onClick={() => {
                      setPickerOpen(false);
                      onSelect(cand.index);
                    }}
                    className={`flex w-full items-start justify-between gap-2 rounded-lg px-2.5 py-2 text-left transition-colors cursor-pointer ${
                      selected
                        ? 'bg-blue-500/10 text-blue-700 dark:text-blue-300'
                        : 'hover:bg-[var(--surface-subtle)]'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-[12.5px] font-medium text-[var(--ink-primary)]">
                          {cand.appName || cand.filename}
                        </span>
                        {cand.versionText && (
                          <span className="font-mono-code shrink-0 text-[10.5px] text-[var(--ink-secondary)]">
                            v{cand.versionText}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-[10.5px] text-[var(--ink-muted)]">
                        <span className="font-mono-code truncate">{cand.filename}</span>
                        <span className="shrink-0">{formatBytes(cand.sizeBytes)}</span>
                        <span className="shrink-0">{formatRelativeTime(cand.mtimeMs)}</span>
                      </div>
                    </div>
                    {selected && <Check className="mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400" />}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
