import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ChevronDown,
  ChevronUp,
  Copy,
  Search,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import type { LogEntry, LogLevel } from '../types';

interface LogConsoleProps {
  logs: LogEntry[];
  onClear: () => void;
  onCopyLogs: (text: string) => void;
}

const LEVEL_FILTERS: { key: 'all' | LogLevel; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'cmd', label: '命令' },
  { key: 'success', label: '成功' },
  { key: 'warn', label: '警告' },
  { key: 'error', label: '错误' },
];

const LEVEL_STYLES: Record<LogLevel, { badge: string; text: string; label: string }> = {
  info: {
    badge: 'bg-slate-500/12 text-slate-600 dark:text-slate-400',
    text: 'text-slate-700 dark:text-slate-300',
    label: 'INFO',
  },
  cmd: {
    badge: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
    text: 'text-blue-700 dark:text-blue-300',
    label: 'CMD ',
  },
  success: {
    badge: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
    text: 'text-emerald-700 dark:text-emerald-300',
    label: ' OK ',
  },
  warn: {
    badge: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
    text: 'text-amber-700 dark:text-amber-300',
    label: 'WARN',
  },
  error: {
    badge: 'bg-rose-500/15 text-rose-700 dark:text-rose-300',
    text: 'text-rose-700 dark:text-rose-300',
    label: 'ERR ',
  },
};

export function LogConsole({ logs, onClear, onCopyLogs }: LogConsoleProps) {
  const [levelFilter, setLevelFilter] = useState<'all' | LogLevel>('all');
  const [query, setQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return logs.filter((entry) => {
      if (levelFilter !== 'all' && entry.level !== levelFilter) return false;
      if (q && !entry.message.toLowerCase().includes(q) && !(entry.deviceId ?? '').toLowerCase().includes(q)) {
        return false;
      }
      return true;
    });
  }, [logs, levelFilter, query]);

  useEffect(() => {
    if (autoScroll && !collapsed && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filtered.length, autoScroll, collapsed]);

  const handleCopy = () => {
    const text = filtered.map((l) => `[${l.timestamp}] [${l.level.toUpperCase()}] ${l.message}`).join('\n');
    onCopyLogs(text);
  };

  return (
    <section className="flex min-h-0 flex-1 flex-col rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-card)] shadow-xs overflow-hidden">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] px-3.5 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="flex items-center gap-1.5 text-[13px] font-semibold text-[var(--ink-primary)] hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer"
          >
            <Terminal className="h-4 w-4 text-slate-500" />
            <span>运行日志</span>
            <span className="font-mono-code rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {filtered.length}
            </span>
            {collapsed ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {!collapsed && (
            <div className="flex items-center rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] p-0.5">
              {LEVEL_FILTERS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setLevelFilter(key)}
                  className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-all cursor-pointer ${
                    levelFilter === key
                      ? 'bg-[var(--surface-card)] text-[var(--ink-primary)] shadow-xs'
                      : 'text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        {!collapsed && (
          <div className="flex items-center gap-1.5">
            <div className="relative flex items-center">
              <Search className="pointer-events-none absolute left-2 h-3.5 w-3.5 text-[var(--ink-muted)]" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="筛选日志关键词…"
                className="h-7 w-40 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] pl-7 pr-6 text-[11.5px] text-[var(--ink-primary)] placeholder:text-[var(--ink-muted)] focus:w-52 focus:border-blue-500 focus:bg-[var(--surface-card)] focus:outline-none transition-all"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="absolute right-1.5 text-[var(--ink-muted)] hover:text-[var(--ink-primary)] cursor-pointer"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => setAutoScroll((v) => !v)}
              title={autoScroll ? '已开启自动滚动到底部' : '已暂停自动滚动'}
              className={`flex h-7 w-7 items-center justify-center rounded-lg border transition-colors cursor-pointer ${
                autoScroll
                  ? 'border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400'
                  : 'border-[var(--border-hairline)] bg-[var(--surface-subtle)] text-[var(--ink-muted)]'
              }`}
            >
              <ArrowDownToLine className="h-3.5 w-3.5" />
            </button>

            <button
              type="button"
              onClick={handleCopy}
              title="复制当前日志"
              className="flex h-7 items-center gap-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] px-2 text-[11.5px] font-medium text-[var(--ink-secondary)] transition-colors hover:text-[var(--ink-primary)] cursor-pointer"
            >
              <Copy className="h-3 w-3" />
              <span>复制</span>
            </button>

            <button
              type="button"
              onClick={onClear}
              title="清空日志"
              className="flex h-7 items-center gap-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-subtle)] px-2 text-[11.5px] font-medium text-[var(--ink-secondary)] transition-colors hover:text-rose-600 dark:hover:text-rose-400 cursor-pointer"
            >
              <Trash2 className="h-3 w-3" />
              <span>清空</span>
            </button>
          </div>
        )}
      </div>

      {/* Log viewport */}
      {!collapsed && (
        <div
          ref={scrollRef}
          className="font-mono-code min-h-[120px] flex-1 overflow-auto bg-[#fafbfc] p-2.5 text-[11.5px] leading-[1.6] dark:bg-[#0d111a]"
        >
          {filtered.length === 0 ? (
            <div className="flex h-full items-center justify-center text-[12px] text-[var(--ink-muted)] font-sans">
              {logs.length === 0 ? '暂无运行日志' : '没有符合当前过滤条件的日志'}
            </div>
          ) : (
            <div className="flex flex-col gap-0.5">
              {filtered.map((entry) => {
                const style = LEVEL_STYLES[entry.level] ?? LEVEL_STYLES.info;
                return (
                  <div
                    key={entry.id}
                    className="flex items-start gap-2 rounded px-1.5 py-0.5 hover:bg-slate-200/50 dark:hover:bg-slate-800/60"
                  >
                    <span className="shrink-0 text-[10.5px] text-[var(--ink-muted)] select-none">
                      {entry.timestamp}
                    </span>
                    <span
                      className={`shrink-0 rounded px-1 py-px text-[9.5px] font-semibold tracking-wider select-none ${style.badge}`}
                    >
                      {style.label}
                    </span>
                    <span className={`whitespace-pre-wrap break-all ${style.text}`}>
                      {entry.message}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
