import { Copy, Plus, RefreshCw, Search, ShieldCheck, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { addSousakuTokens, deleteSousakuAccount, listProviderAccounts, refreshSousakuAccount, updateSousakuAccount, type ProviderAccount } from '../../services/api';
import { useProviders } from '../../hooks/useProviders';
import { providerLabel } from '../../utils/providers';

const statusLabel: Record<string, string> = {
    available: '可用',
    busy: '运行中',
    low_quota: '低额度',
    invalid: '失效',
    disabled: '停用',
};

const statusTone: Record<string, string> = {
    available: 'bg-[var(--account-status-available-bg)] text-[var(--account-status-available-text)] border-[var(--account-status-available-border)]',
    busy: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
    low_quota: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    invalid: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
    disabled: 'bg-[var(--account-status-disabled-bg)] text-[var(--account-status-disabled-text)] border-[var(--account-status-disabled-border)]',
};

const providers = ['sousaku', 'cliproxy', 'nanobanana2', 'apimart'];

function formatCredits(value: number) {
    return new Intl.NumberFormat('zh-CN').format(Math.round(value));
}

function formatPlanLabel(value: unknown) {
    const text = String(value || '').trim();
    if (!text) return '';
    return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

function accountPlanTags(account: ProviderAccount) {
    const providerName = String(account.provider || '').toLowerCase();
    const metadataPlan = formatPlanLabel(account.metadata?.package_level);
    const tags = [metadataPlan, ...(account.tags || []).map(formatPlanLabel)]
        .filter(Boolean)
        .filter((tag) => tag.toLowerCase() !== providerName && tag.toLowerCase() !== 'sousaku');
    return Array.from(new Set(tags)).slice(0, 1);
}

export function AccountsPage() {
    const [provider, setProvider] = useState('sousaku');
    const [accounts, setAccounts] = useState<ProviderAccount[]>([]);
    const [query, setQuery] = useState('');
    const [status, setStatus] = useState('all');
    const [refreshing, setRefreshing] = useState(false);
    const [adding, setAdding] = useState(false);
    const [refreshingAccountId, setRefreshingAccountId] = useState<string | null>(null);
    const { providers: runtimeProviders } = useProviders();

    const load = async (options?: { refresh?: boolean }) => {
        if (options?.refresh) setRefreshing(true);
        try {
            const response = await listProviderAccounts(provider, options);
            if (response.success) {
                setAccounts(response.data || []);
            }
        } finally {
            if (options?.refresh) setRefreshing(false);
        }
    };

    const handleAddTokens = async () => {
        const tokens = window.prompt('粘贴 Sousaku token，多个 token 可用换行、逗号或分号分隔：');
        if (!tokens?.trim()) return;
        setAdding(true);
        try {
            const response = await addSousakuTokens(tokens);
            if (!response.success) {
                window.alert(response.error?.message || '导入失败');
                return;
            }
            window.alert(`导入完成：新增 ${response.added || 0} 个，跳过重复 ${response.skipped || 0} 个，已刷新新增 ${response.refreshed || 0} 个。`);
            await load({ refresh: false });
        } finally {
            setAdding(false);
        }
    };

    const handleCopyAccount = async (account: ProviderAccount) => {
        const meta = account.metadata || {};
        const shareCode = String(meta.share_code || '');
        const lines = [
            `账号：${account.label}`,
            `状态：${statusLabel[account.status] || account.status}`,
            `额度：${account.quota?.remaining ?? '-'} ${account.quota?.unit || ''}`,
            `邀请码：${shareCode || '-'}`,
            shareCode ? `邀请链接：https://sousaku.ai/zh-CN/signin?share_code=${shareCode}` : '',
            `Token：${meta.token_masked || '-'}`,
        ].filter(Boolean);
        try {
            await navigator.clipboard.writeText(lines.join('\n'));
        } catch {
            window.prompt('复制账号信息：', lines.join('\n'));
        }
    };

    const handleToggleAccount = async (account: ProviderAccount) => {
        if (provider !== 'sousaku') return;
        const disabled = account.status !== 'disabled';
        const response = await updateSousakuAccount(account.id, { disabled });
        if (!response.success) {
            window.alert(response.error?.message || '账号状态更新失败');
            return;
        }
        await load();
    };

    const handleRefreshAccount = async (account: ProviderAccount) => {
        if (provider !== 'sousaku') return;
        setRefreshingAccountId(account.id);
        try {
            const response = await refreshSousakuAccount(account.id);
            if (!response.success) {
                window.alert(response.error?.message || '账号刷新失败');
                return;
            }
            await load();
        } finally {
            setRefreshingAccountId(null);
        }
    };

    const handleDeleteAccount = async (account: ProviderAccount) => {
        if (provider !== 'sousaku') return;
        const response = await deleteSousakuAccount(account.id);
        if (!response.success) {
            window.alert(response.error?.message || '账号删除失败');
            return;
        }
        setAccounts((items) => items.filter((item) => item.id !== account.id));
    };

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [provider]);

    const filtered = useMemo(() => {
        return accounts.filter((account) => {
            if (status !== 'all' && account.status !== status) return false;
            const text = `${account.label} ${account.provider} ${account.tags?.join(' ')} ${JSON.stringify(account.metadata || {})}`.toLowerCase();
            return !query || text.includes(query.toLowerCase());
        });
    }, [accounts, query, status]);

    const totals = {
        available: accounts.filter((a) => a.status === 'available').length,
        busy: accounts.filter((a) => a.status === 'busy').length,
        low: accounts.filter((a) => a.status === 'low_quota').length,
        invalid: accounts.filter((a) => a.status === 'invalid').length,
        disabled: accounts.filter((a) => a.status === 'disabled').length,
    };

    const summary = useMemo(() => {
        const totalCredits = accounts.reduce((sum, account) => {
            const value = Number(account.quota?.remaining ?? account.quota?.total ?? 0);
            return Number.isFinite(value) ? sum + value : sum;
        }, 0);
        return {
            accountCount: accounts.length,
            availableCount: accounts.filter((account) => account.status === 'available').length,
            totalCredits,
        };
    }, [accounts]);

    return (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-4">
            <div className="mb-4 flex flex-wrap items-center gap-3">
                <div>
                    <div className="text-lg font-semibold text-[var(--text-primary)]">账号池</div>
                    <div className="text-xs text-[var(--text-muted)]">通用 Provider 账号管理</div>
                </div>
                <div className="ml-auto flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
                    {providers.map((item) => (
                        <button
                            key={item}
                            onClick={() => setProvider(item)}
                            className={`rounded-full px-3 py-1.5 text-sm capitalize transition-colors ${provider === item ? 'bg-[var(--accent-primary)] text-white' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
                        >
                            {providerLabel(item, runtimeProviders)}
                        </button>
                    ))}
                </div>
                <button
                    onClick={() => void handleAddTokens()}
                    disabled={adding || provider !== 'sousaku'}
                    className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--accent-primary)] px-3 py-2 text-sm text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                >
                    <Plus className="h-4 w-4" />
                    {adding ? '导入中...' : '添加账号'}
                </button>
                <button
                    onClick={() => void load({ refresh: true })}
                    disabled={refreshing || provider !== 'sousaku'}
                    className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                    <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                    {refreshing ? '刷新中...' : '刷新全部账号'}
                </button>
            </div>

            <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                {[
                    ['账号数', summary.accountCount, '个'],
                    ['可用账号', summary.availableCount, '个'],
                    ['总额度', formatCredits(summary.totalCredits), 'credits'],
                ].map(([label, value, unit]) => (
                    <div key={label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
                        <div className="text-xs text-[var(--text-muted)]">{label}</div>
                        <div className="mt-1 flex items-baseline gap-2">
                            <span className="font-mono text-2xl font-semibold text-[var(--text-primary)]">{value}</span>
                            <span className="text-xs text-[var(--text-muted)]">{unit}</span>
                        </div>
                    </div>
                ))}
            </div>

            <div className="mb-4 flex flex-wrap items-center gap-3">
                <div className="relative min-w-72 flex-1">
                    <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
                    <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="搜索账号、邮箱或邀请码..."
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--accent-primary)]"
                    />
                </div>
                {[
                    ['all', `全部 ${accounts.length}`],
                    ['available', `可用 ${totals.available}`],
                    ['busy', `运行中 ${totals.busy}`],
                    ['low_quota', `低额度 ${totals.low}`],
                    ['invalid', `失效 ${totals.invalid}`],
                    ['disabled', `停用 ${totals.disabled}`],
                ].map(([value, label]) => (
                    <button
                        key={value}
                        onClick={() => setStatus(value)}
                        className={`rounded-full px-3 py-1.5 text-sm transition-colors ${status === value ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
                    >
                        {label}
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {filtered.map((account) => {
                    const remaining = Number(account.quota?.remaining || 0);
                    const total = Math.max(remaining, 224);
                    const percent = Math.max(0, Math.min(100, Math.round((remaining / total) * 100)));
                    const meta = account.metadata || {};
                    const planTags = accountPlanTags(account);
                    return (
                        <article key={account.id} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4 transition-colors hover:border-[var(--text-muted)]">
                            <div className="mb-3 flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <div className="truncate text-base font-semibold text-[var(--text-primary)]">{account.label}</div>
                                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                        {planTags.map((tag) => (
                                            <span key={tag} className="rounded-full bg-[var(--account-plan-bg)] px-2 py-0.5 text-xs text-[var(--account-plan-text)]">{tag}</span>
                                        ))}
                                    </div>
                                </div>
                                <span className={`shrink-0 rounded-full border px-2 py-1 text-xs ${statusTone[account.status] || statusTone.disabled}`}>
                                    {statusLabel[account.status] || account.status}
                                </span>
                            </div>

                            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3">
                                <div className="mb-2 flex items-center justify-between text-sm">
                                    <span className="text-[var(--text-muted)]">额度</span>
                                    <span className="font-mono text-[var(--account-credit-text)]">{remaining || '-'} {account.quota?.unit || ''}</span>
                                </div>
                                <div className="h-2 overflow-hidden rounded-full bg-[var(--account-progress-track)]">
                                    <div className="h-full rounded-full bg-[var(--account-progress-fill)]" style={{ width: `${percent}%` }} />
                                </div>
                                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[var(--text-secondary)]">
                                    <div>当前任务：{account.running_jobs || 0}</div>
                                    <div>邀请码：{String(meta.share_code || '-')}</div>
                                    <div className="col-span-2 truncate">Token：{String(meta.token_masked || '-')}</div>
                                </div>
                            </div>

                            <div className="mt-3 flex items-center justify-between">
                                <div className="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                                    <ShieldCheck className="h-3.5 w-3.5" />
                                    {account.last_used_at ? new Date(account.last_used_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '未记录'}
                                </div>
                                <div className="flex items-center gap-1 text-[var(--text-muted)]">
                                    <button
                                        className="rounded p-1.5 hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-40"
                                        title="刷新此账号"
                                        disabled={provider !== 'sousaku' || !!refreshingAccountId}
                                        onClick={() => void handleRefreshAccount(account)}
                                    >
                                        <RefreshCw className={`h-4 w-4 ${refreshingAccountId === account.id ? 'animate-spin' : ''}`} />
                                    </button>
                                    <button
                                        className="rounded p-1.5 hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)]"
                                        title="复制账号信息"
                                        onClick={() => void handleCopyAccount(account)}
                                    >
                                        <Copy className="h-4 w-4" />
                                    </button>
                                    <button
                                        className="rounded p-1.5 hover:bg-[var(--bg-card-hover)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-40"
                                        title={account.status === 'disabled' ? '启用账号' : '停用账号'}
                                        disabled={provider !== 'sousaku'}
                                        onClick={() => void handleToggleAccount(account)}
                                    >
                                        {account.status === 'disabled' ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
                                    </button>
                                    <button
                                        className="rounded p-1.5 hover:bg-[var(--bg-card-hover)] hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-40"
                                        title="删除账号"
                                        disabled={provider !== 'sousaku'}
                                        onClick={() => void handleDeleteAccount(account)}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        </article>
                    );
                })}
            </div>
            {!filtered.length && (
                <div className="rounded-xl border border-dashed border-[var(--border-subtle)] p-12 text-center text-sm text-[var(--text-muted)]">
                    当前 Provider 暂无账号数据
                </div>
            )}
        </section>
    );
}
