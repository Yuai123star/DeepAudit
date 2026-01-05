/**
 * Project Detail Page
 * Cyberpunk Terminal Aesthetic
 */

import { useMemo, useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import {
  ArrowLeft,
  Edit,
  ExternalLink,
  Code,
  Shield,
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  XCircle,
  Play,
  FileText,
  Upload,
  GitBranch,
  Terminal
} from "lucide-react";
import { api } from "@/shared/config/database";
import { runRepositoryAudit, scanStoredZipFile } from "@/features/projects/services";
import type { Project, AuditTask, CreateProjectForm, AuditIssue } from "@/shared/types";
import type { AgentFinding, AgentTask } from "@/shared/api/agentTasks";
import { getAgentFindings, getAgentTasks } from "@/shared/api/agentTasks";
import { hasZipFile } from "@/shared/utils/zipStorage";
import { isRepositoryProject, getSourceTypeLabel, getRepositoryPlatformLabel } from "@/shared/utils/projectUtils";
import { toast } from "sonner";
import CreateTaskDialog from "@/components/audit/CreateTaskDialog";
import FileSelectionDialog from "@/components/audit/FileSelectionDialog";
import TerminalProgressDialog from "@/components/audit/TerminalProgressDialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { SUPPORTED_LANGUAGES, REPOSITORY_PLATFORMS } from "@/shared/constants";

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [auditTasks, setAuditTasks] = useState<AuditTask[]>([]);
  const [agentTasks, setAgentTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [showCreateTaskDialog, setShowCreateTaskDialog] = useState(false);
  const [showTerminalDialog, setShowTerminalDialog] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<CreateProjectForm>({
    name: "",
    description: "",
    source_type: "repository",
    repository_url: "",
    repository_type: "github",
    default_branch: "main",
    programming_languages: []
  });
  const [activeTab, setActiveTab] = useState("overview");
  type AggregatedAuditIssue = AuditIssue & {
    task_created_at?: string;
    task_completed_at?: string;
  };

  const [latestIssues, setLatestIssues] = useState<AggregatedAuditIssue[]>([]);
  type AggregatedAgentFinding = AgentFinding & {
    task_created_at?: string;
    task_completed_at?: string | null;
  };

  const [latestFindings, setLatestFindings] = useState<AggregatedAgentFinding[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [issuesSummary, setIssuesSummary] = useState<{
    completedAuditTasksCount: number;
    completedAgentTasksCount: number;
    fetchedAuditTasksCount: number;
    fetchedAgentTasksCount: number;
    isLimited: boolean;
    maxTasks: number;
  }>({
    completedAuditTasksCount: 0,
    completedAgentTasksCount: 0,
    fetchedAuditTasksCount: 0,
    fetchedAgentTasksCount: 0,
    isLimited: false,
    maxTasks: 20
  });

  const [showFileSelectionDialog, setShowFileSelectionDialog] = useState(false);
  const [showAuditOptionsDialog, setShowAuditOptionsDialog] = useState(false);

  useEffect(() => {
    if (activeTab === 'issues' && (auditTasks.length > 0 || agentTasks.length > 0)) {
      loadLatestIssues();
    }
  }, [activeTab, auditTasks, agentTasks]);

  const loadLatestIssues = async () => {
    const completedAuditTasks = auditTasks
      .filter((t: AuditTask) => t.status === 'completed')
      .sort((a: AuditTask, b: AuditTask) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
    const completedAgentTasks = agentTasks
      .filter((t: AgentTask) => t.status === 'completed')
      .sort((a: AgentTask, b: AgentTask) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

    const MAX_TASKS = 20;
    const limitedAuditTasks = completedAuditTasks.slice(0, MAX_TASKS);
    const limitedAgentTasks = completedAgentTasks.slice(0, MAX_TASKS);

    setIssuesSummary({
      completedAuditTasksCount: completedAuditTasks.length,
      completedAgentTasksCount: completedAgentTasks.length,
      fetchedAuditTasksCount: limitedAuditTasks.length,
      fetchedAgentTasksCount: limitedAgentTasks.length,
      isLimited: completedAuditTasks.length > MAX_TASKS || completedAgentTasks.length > MAX_TASKS,
      maxTasks: MAX_TASKS
    });

    if (limitedAuditTasks.length === 0 && limitedAgentTasks.length === 0) {
      setLatestIssues([]);
      setLatestFindings([]);
      return;
    }

    setLoadingIssues(true);
    try {
      const [issuesResults, findingsResults] = await Promise.all([
        Promise.allSettled(
          limitedAuditTasks.map(async (t: AuditTask) => {
          const issues = await api.getAuditIssues(t.id);
          const enriched: AggregatedAuditIssue[] = (issues || []).map((i) => ({
            ...(i as AuditIssue),
            task_created_at: t.created_at,
            task_completed_at: t.completed_at
          }));
          return enriched;
          })
        ),
        Promise.allSettled(
          limitedAgentTasks.map(async (t: AgentTask) => {
            const findings = await getAgentFindings(t.id);
            const enriched: AggregatedAgentFinding[] = (findings || []).map((f) => ({
              ...(f as AgentFinding),
              task_created_at: t.created_at,
              task_completed_at: t.completed_at
            }));
            return enriched;
          })
        )
      ]);

      const flatIssues = issuesResults
        .filter((r: PromiseSettledResult<AggregatedAuditIssue[]>): r is PromiseFulfilledResult<AggregatedAuditIssue[]> => r.status === 'fulfilled')
        .flatMap((r: PromiseFulfilledResult<AggregatedAuditIssue[]>) => r.value);
      const flatFindings = findingsResults
        .filter((r: PromiseSettledResult<AggregatedAgentFinding[]>): r is PromiseFulfilledResult<AggregatedAgentFinding[]> => r.status === 'fulfilled')
        .flatMap((r: PromiseFulfilledResult<AggregatedAgentFinding[]>) => r.value);

      const severityRank: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
      flatIssues.sort((a: AggregatedAuditIssue, b: AggregatedAuditIssue) => {
        const sa = severityRank[a.severity] ?? 0;
        const sb = severityRank[b.severity] ?? 0;
        if (sa !== sb) return sb - sa;

        const ta = new Date(a.created_at).getTime();
        const tb = new Date(b.created_at).getTime();
        if (ta !== tb) return tb - ta;

        const tta = a.task_created_at ? new Date(a.task_created_at).getTime() : 0;
        const ttb = b.task_created_at ? new Date(b.task_created_at).getTime() : 0;
        return ttb - tta;
      });

      setLatestIssues(flatIssues);
      flatFindings.sort((a: AggregatedAgentFinding, b: AggregatedAgentFinding) => {
        const sa = severityRank[String(a.severity || '').toLowerCase()] ?? 0;
        const sb = severityRank[String(b.severity || '').toLowerCase()] ?? 0;
        if (sa !== sb) return sb - sa;
        const ta = new Date(a.created_at).getTime();
        const tb = new Date(b.created_at).getTime();
        if (ta !== tb) return tb - ta;
        const tta = a.task_created_at ? new Date(a.task_created_at).getTime() : 0;
        const ttb = b.task_created_at ? new Date(b.task_created_at).getTime() : 0;
        return ttb - tta;
      });
      setLatestFindings(flatFindings);
    } catch (error) {
      console.error('Failed to load issues:', error);
      toast.error("加载问题列表失败");
    } finally {
      setLoadingIssues(false);
    }
  };

  type LatestProblem = {
    kind: 'audit' | 'agent';
    id: string;
    task_id: string;
    task_created_at?: string;
    created_at: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    title: string;
    description?: string | null;
    file_path?: string | null;
    line_number?: number | null;
    line_end?: number | null;
    category?: string | null;
  };

  const latestProblems: LatestProblem[] = useMemo(() => {
    const parsePathLineFromTitle = (title: string) => {
      // Pattern examples:
      // "path/to/File.java:66 - Something"
      // "path/to/File.java:137-138 - Something"
      const m = title.match(/^(.*?):(\d+)(?:-(\d+))?\s*-\s*(.+)$/);
      if (!m) return null;
      const [, path, lineStartStr, lineEndStr, rest] = m;
      const lineStart = Number(lineStartStr);
      const lineEnd = lineEndStr ? Number(lineEndStr) : null;
      return {
        file_path: path,
        line_start: Number.isFinite(lineStart) ? lineStart : null,
        line_end: lineEnd != null && Number.isFinite(lineEnd) ? lineEnd : null,
        rest_title: rest,
      };
    };

    const normalizeSeverity = (s: unknown): LatestProblem['severity'] => {
      const v = String(s || '').toLowerCase();
      if (v === 'critical') return 'critical';
      if (v === 'high') return 'high';
      if (v === 'medium') return 'medium';
      return 'low';
    };

    const audit: LatestProblem[] = latestIssues.map((i) => ({
      // AuditIssue 在后端 schema 里可能叫 message（frontend type 没显式定义），这里做兼容兜底
      // 同时优先展示更“可读”的说明字段，避免 UI 出现大量 '-'
      kind: 'audit',
      id: i.id,
      task_id: i.task_id,
      task_created_at: i.task_created_at,
      created_at: i.created_at,
      severity: normalizeSeverity(i.severity),
      title: i.title || '(未命名问题)',
      description:
        i.description ??
        (i as any).message ??
        (i as any).ai_explanation ??
        (i as any).suggestion ??
        (i as any).code_snippet ??
        null,
      file_path: i.file_path,
      line_number: i.line_number ?? null,
      category: (i as any).issue_type ?? null,
    }));

    const agent: LatestProblem[] = latestFindings.map((f) => {
      const rawTitle = f.title || '(未命名漏洞)';
      const parsed = (!f.file_path || f.file_path === '-') ? parsePathLineFromTitle(rawTitle) : null;

      return {
        kind: 'agent',
        id: f.id,
        task_id: f.task_id,
        task_created_at: f.task_created_at,
        created_at: f.created_at,
        severity: normalizeSeverity(f.severity),
        // 如果 title 里带了 "path:line - xxx"，则剥离掉路径前缀，仅保留 xxx，避免标题重复且过长
        title: parsed?.rest_title || rawTitle,
        description: f.description,
        // 如果后端没给 file_path，尽量从 title 解析出来填到“文件”列
        file_path: f.file_path ?? parsed?.file_path ?? null,
        line_number: ((f.line_start ?? parsed?.line_start ?? null) as any),
        line_end: ((f.line_end ?? parsed?.line_end ?? null) as any),
        category: (f as any).vulnerability_type ?? null,
      };
    });

    const merged = [...audit, ...agent];
    // 按时间倒序（最新在前），时间相同再按严重程度
    const severityRank: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
    merged.sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      if (ta !== tb) return tb - ta;
      const sa = severityRank[a.severity] ?? 0;
      const sb = severityRank[b.severity] ?? 0;
      if (sa !== sb) return sb - sa;
      const tta = a.task_created_at ? new Date(a.task_created_at).getTime() : 0;
      const ttb = b.task_created_at ? new Date(b.task_created_at).getTime() : 0;
      return ttb - tta;
    });
    return merged;
  }, [latestIssues, latestFindings]);

  const handleOpenSettings = () => {
    if (!project) return;

    setEditForm({
      name: project.name,
      description: project.description || "",
      source_type: project.source_type || "repository",
      repository_url: project.repository_url || "",
      repository_type: project.repository_type || "github",
      default_branch: project.default_branch || "main",
      programming_languages: project.programming_languages ? JSON.parse(project.programming_languages) : []
    });

    setActiveTab("settings");
  };

  const formatLanguageName = (lang: string): string => {
    const nameMap: Record<string, string> = {
      'javascript': 'JavaScript',
      'typescript': 'TypeScript',
      'python': 'Python',
      'java': 'Java',
      'go': 'Go',
      'rust': 'Rust',
      'cpp': 'C++',
      'csharp': 'C#',
      'php': 'PHP',
      'ruby': 'Ruby',
      'swift': 'Swift',
      'kotlin': 'Kotlin'
    };
    return nameMap[lang] || lang.charAt(0).toUpperCase() + lang.slice(1);
  };

  const supportedLanguages = SUPPORTED_LANGUAGES.map(formatLanguageName);

  useEffect(() => {
    if (id) {
      loadProjectData();
    }
  }, [id]);

  const loadProjectData = async () => {
    if (!id) return;

    try {
      setLoading(true);
      const [projectData, tasksData, agentTasksData] = await Promise.all([
        api.getProjectById(id),
        api.getAuditTasks(id),
        getAgentTasks({ project_id: id }).catch(() => [])
      ]);

      setProject(projectData);
      setAuditTasks(Array.isArray(tasksData) ? tasksData : []);
      setAgentTasks(Array.isArray(agentTasksData) ? agentTasksData : []);
    } catch (error) {
      console.error('Failed to load project data:', error);
      toast.error("加载项目数据失败");
    } finally {
      setLoading(false);
    }
  };

  type UnifiedTask =
    | { kind: 'audit'; task: AuditTask }
    | { kind: 'agent'; task: AgentTask };

  const unifiedTasks: UnifiedTask[] = useMemo(() => {
    const merged: UnifiedTask[] = [
      ...auditTasks.map((t) => ({ kind: 'audit' as const, task: t })),
      ...agentTasks.map((t) => ({ kind: 'agent' as const, task: t })),
    ];
    merged.sort((a, b) => new Date((b.task as any).created_at).getTime() - new Date((a.task as any).created_at).getTime());
    return merged;
  }, [auditTasks, agentTasks]);

  const combinedStats = useMemo(() => {
    const totalTasks = auditTasks.length + agentTasks.length;
    const completedTasks =
      auditTasks.filter((t) => t.status === 'completed').length +
      agentTasks.filter((t) => t.status === 'completed').length;
    const totalIssues =
      auditTasks.reduce((sum, t) => sum + (t.issues_count || 0), 0) +
      agentTasks.reduce((sum, t) => sum + (t.findings_count || 0), 0);
    const avgQualityScore = totalTasks > 0
      ? (
        (auditTasks.reduce((sum, t) => sum + (t.quality_score || 0), 0) +
          agentTasks.reduce((sum, t) => sum + (t.quality_score || 0), 0)) / totalTasks
      )
      : 0;
    return { totalTasks, completedTasks, totalIssues, avgQualityScore };
  }, [auditTasks, agentTasks]);

  const handleRunAudit = () => {
    setShowAuditOptionsDialog(true);
  };

  const handleStartFullAudit = () => {
    setShowAuditOptionsDialog(false);
    startAudit(undefined);
  };

  const handleOpenCustomAudit = () => {
    setShowAuditOptionsDialog(false);
    setShowFileSelectionDialog(true);
  };

  const handleStartCustomAudit = (files: string[]) => {
    startAudit(files);
  };

  const startAudit = async (filePaths?: string[]) => {
    if (!project || !id) return;

    if (project.repository_url) {
      try {
        setScanning(true);
        console.log('开始启动仓库审计任务...', filePaths ? `指定 ${filePaths.length} 个文件` : '全量扫描');
        const taskId = await runRepositoryAudit({
          projectId: id,
          repoUrl: project.repository_url,
          branch: project.default_branch || 'main',
          createdBy: undefined,
          filePaths: filePaths
        });

        console.log('审计任务创建成功，taskId:', taskId);

        setCurrentTaskId(taskId);
        setShowTerminalDialog(true);

        loadProjectData();
      } catch (e: any) {
        console.error('启动审计失败:', e);
        toast.error(e?.message || '启动审计失败');
      } finally {
        setScanning(false);
      }
    } else {
      try {
        setScanning(true);
        const hasFile = await hasZipFile(id);

        if (hasFile) {
          console.log('找到后端存储的ZIP文件，开始启动审计...', filePaths ? `指定 ${filePaths.length} 个文件` : '全量扫描');
          try {
            const taskId = await scanStoredZipFile({
              projectId: id,
              excludePatterns: ['node_modules/**', '.git/**', 'dist/**', 'build/**'],
              createdBy: 'local-user',
              filePaths: filePaths
            });

            console.log('审计任务创建成功，taskId:', taskId);

            setCurrentTaskId(taskId);
            setShowTerminalDialog(true);

            loadProjectData();
          } catch (e: any) {
            console.error('启动审计失败:', e);
            toast.error(e?.message || '启动审计失败');
          } finally {
            setScanning(false);
          }
        } else {
          setScanning(false);
          toast.warning('此项目未配置仓库地址，也未上传ZIP文件。请先在项目设置中配置仓库地址，或通过"新建任务"上传ZIP文件。');
        }
      } catch (error) {
        console.error('启动审计失败:', error);
        setScanning(false);
        toast.error('读取ZIP文件失败，请检查项目配置');
      }
    }
  };

  const handleSaveSettings = async () => {
    if (!id) return;

    if (!editForm.name.trim()) {
      toast.error("项目名称不能为空");
      return;
    }

    try {
      await api.updateProject(id, editForm);
      toast.success("项目信息已保存");
      loadProjectData();
    } catch (error) {
      console.error('Failed to update project:', error);
      toast.error("保存失败");
    }
  };

  const handleToggleLanguage = (lang: string) => {
    const currentLanguages = editForm.programming_languages || [];
    const newLanguages = currentLanguages.includes(lang)
      ? currentLanguages.filter(l => l !== lang)
      : [...currentLanguages, lang];

    setEditForm({ ...editForm, programming_languages: newLanguages });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge className="cyber-badge-success">完成</Badge>;
      case 'running':
        return <Badge className="cyber-badge-info">运行中</Badge>;
      case 'failed':
        return <Badge className="cyber-badge-danger">失败</Badge>;
      case 'cancelled':
        return <Badge className="cyber-badge-muted">已取消</Badge>;
      default:
        return <Badge className="cyber-badge-muted">等待中</Badge>;
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      case 'running': return <Activity className="w-4 h-4 text-sky-400" />;
      case 'failed': return <AlertTriangle className="w-4 h-4 text-rose-400" />;
      case 'cancelled': return <XCircle className="w-4 h-4 text-muted-foreground" />;
      default: return <Clock className="w-4 h-4 text-muted-foreground" />;
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const handleCreateTask = () => {
    setShowCreateTaskDialog(true);
  };

  const handleTaskCreated = () => {
    toast.success("审计任务已创建", {
      description: '因为网络和代码文件大小等因素，审计时长通常至少需要1分钟，请耐心等待...',
      duration: 5000
    });
    loadProjectData();
  };

  const handleFastScanStarted = (taskId: string) => {
    setCurrentTaskId(taskId);
    setShowTerminalDialog(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-4">
          <div className="loading-spinner mx-auto" />
          <p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">加载项目数据...</p>
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="cyber-card p-8 text-center">
          <AlertTriangle className="w-16 h-16 text-rose-400 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-foreground mb-2 uppercase">项目未找到</h2>
          <p className="text-muted-foreground mb-4 font-mono">请检查项目ID是否正确</p>
          <Link to="/projects">
            <Button className="cyber-btn-primary">
              <ArrowLeft className="w-4 h-4 mr-2" />
              返回项目列表
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 cyber-bg-elevated min-h-screen font-mono relative">
      {/* Grid background */}
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

      {/* 顶部操作栏 */}
      <div className="relative z-10 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/projects">
            <Button variant="outline" size="sm" className="cyber-btn-ghost h-10 w-10 p-0 flex items-center justify-center">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-foreground uppercase tracking-wider">{project.name}</h1>
            <Badge className={`${project.is_active ? 'cyber-badge-success' : 'cyber-badge-muted'}`}>
              {project.is_active ? '活跃' : '暂停'}
            </Badge>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <Button onClick={handleRunAudit} disabled={scanning} className="cyber-btn-primary">
            <Shield className="w-4 h-4 mr-2" />
            {scanning ? '正在启动...' : '启动审计'}
          </Button>
          <Button variant="outline" onClick={handleOpenSettings} className="cyber-btn-outline">
            <Edit className="w-4 h-4 mr-2" />
            编辑
          </Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 relative z-10">
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">审计任务</p>
              <p className="stat-value">{combinedStats.totalTasks}</p>
            </div>
            <div className="stat-icon text-sky-400">
              <Activity className="w-6 h-6" />
            </div>
          </div>
        </div>

        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">已完成</p>
              <p className="stat-value">{combinedStats.completedTasks}</p>
            </div>
            <div className="stat-icon text-emerald-400">
              <CheckCircle className="w-6 h-6" />
            </div>
          </div>
        </div>

        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">发现问题</p>
              <p className="stat-value">{combinedStats.totalIssues}</p>
            </div>
            <div className="stat-icon text-amber-400">
              <AlertTriangle className="w-6 h-6" />
            </div>
          </div>
        </div>

        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">平均质量分</p>
              <p className="stat-value">{combinedStats.avgQualityScore.toFixed(1)}</p>
            </div>
            <div className="stat-icon text-violet-400">
              <Code className="w-6 h-6" />
            </div>
          </div>
        </div>
      </div>

      {/* 主要内容 */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full relative z-10">
        <TabsList className="grid w-full grid-cols-4 bg-muted border border-border p-1 h-auto gap-1 rounded">
          <TabsTrigger value="overview" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2 text-muted-foreground transition-all rounded-sm">项目概览</TabsTrigger>
          <TabsTrigger value="tasks" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2 text-muted-foreground transition-all rounded-sm">审计任务</TabsTrigger>
          <TabsTrigger value="issues" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2 text-muted-foreground transition-all rounded-sm">问题管理</TabsTrigger>
          <TabsTrigger value="settings" className="data-[state=active]:bg-primary data-[state=active]:text-foreground font-mono font-bold uppercase py-2 text-muted-foreground transition-all rounded-sm">项目设置</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="flex flex-col gap-6 mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* 项目信息 */}
            <div className="cyber-card p-4">
              <div className="section-header">
                <Terminal className="w-5 h-5 text-primary" />
                <h3 className="section-title">项目信息</h3>
              </div>
              <div className="space-y-4 font-mono">
                <div className="space-y-3">
                  {project.repository_url && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground uppercase">仓库地址</span>
                      <a
                        href={project.repository_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-primary hover:underline flex items-center font-bold"
                      >
                        查看仓库
                        <ExternalLink className="w-3 h-3 ml-1" />
                      </a>
                    </div>
                  )}

                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground uppercase">项目类型</span>
                    <Badge className={`${isRepositoryProject(project) ? 'cyber-badge-info' : 'cyber-badge-warning'}`}>
                      {getSourceTypeLabel(project.source_type)}
                    </Badge>
                  </div>

                  {isRepositoryProject(project) && (
                    <>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground uppercase">仓库平台</span>
                        <Badge className="cyber-badge-muted">
                          {getRepositoryPlatformLabel(project.repository_type)}
                        </Badge>
                      </div>

                      <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground uppercase">默认分支</span>
                        <span className="text-sm font-bold text-foreground bg-muted px-2 py-0.5 rounded border border-border">{project.default_branch}</span>
                      </div>
                    </>
                  )}

                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground uppercase">创建时间</span>
                    <span className="text-sm text-foreground">{formatDate(project.created_at)}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground uppercase">所有者</span>
                    <span className="text-sm text-foreground">{project.owner?.full_name || project.owner?.phone || '未知'}</span>
                  </div>
                </div>

                {project.programming_languages && (
                  <div className="pt-4 border-t border-border">
                    <h4 className="text-sm font-bold mb-2 uppercase text-muted-foreground">支持的编程语言</h4>
                    <div className="flex flex-wrap gap-2">
                      {JSON.parse(project.programming_languages).map((lang: string) => (
                        <Badge key={lang} className="cyber-badge-primary">
                          {lang}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* 最近活动 */}
            <div className="cyber-card p-4">
              <div className="section-header">
                <Clock className="w-5 h-5 text-emerald-400" />
                <h3 className="section-title">最近活动</h3>
              </div>
              <div>
                {unifiedTasks.length > 0 ? (
                  <div className="space-y-2">
                    {unifiedTasks.slice(0, 5).map((t) => (
                      <Link
                        key={`${t.kind}:${t.task.id}`}
                        to={t.kind === 'audit' ? `/tasks/${t.task.id}` : `/agent-audit/${t.task.id}`}
                        className="flex items-center justify-between p-3 bg-muted/50 rounded-lg hover:bg-muted transition-all group"
                      >
                        <div className="flex items-center space-x-3">
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${t.task.status === 'completed' ? 'bg-emerald-500/20' :
                            t.task.status === 'running' ? 'bg-sky-500/20' :
                              t.task.status === 'failed' ? 'bg-rose-500/20' :
                                'bg-muted'
                            }`}>
                            {getStatusIcon(t.task.status)}
                          </div>
                          <div>
                            <p className="text-sm font-bold text-foreground group-hover:text-primary transition-colors uppercase">
                              {t.kind === 'audit'
                                ? ((t.task as AuditTask).task_type === 'repository' ? '审计任务' : '即时分析')
                                : 'Agent 审计'}
                            </p>
                            <p className="text-xs text-muted-foreground font-mono">
                              {formatDate(t.task.created_at)}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={t.kind === 'agent' ? 'cyber-badge-info' : 'cyber-badge-muted'}>
                            {t.kind === 'agent' ? 'AGENT' : 'AUDIT'}
                          </Badge>
                          {getStatusBadge(t.task.status)}
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <Activity className="empty-state-icon" />
                    <p className="empty-state-description">暂无活动记录</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="tasks" className="flex flex-col gap-6 mt-6">
          <div className="flex items-center justify-between">
            <div className="section-header mb-0 pb-0 border-0">
              <FileText className="w-5 h-5 text-primary" />
              <h3 className="section-title">审计任务列表</h3>
            </div>
            <Button onClick={handleCreateTask} className="cyber-btn-primary">
              <Play className="w-4 h-4 mr-2" />
              新建任务
            </Button>
          </div>

          {unifiedTasks.length > 0 ? (
            <div className="space-y-4">
              {unifiedTasks.map((t) => {
                const isAudit = t.kind === 'audit';
                const task = t.task as any;
                const issuesOrFindings = isAudit ? (task.issues_count ?? 0) : (task.findings_count ?? 0);
                const totalFiles = task.total_files ?? 0;
                const totalLines = task.total_lines ?? '-';
                const qualityScore = typeof task.quality_score === 'number' ? task.quality_score : 0;

                return (
                <div key={`${t.kind}:${task.id}`} className="cyber-card p-6">
                  <div className="flex items-center justify-between mb-4 pb-4 border-b border-border">
                    <div className="flex items-center space-x-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${task.status === 'completed' ? 'bg-emerald-500/20' :
                        task.status === 'running' ? 'bg-sky-500/20' :
                          task.status === 'failed' ? 'bg-rose-500/20' :
                            'bg-muted'
                        }`}>
                        {getStatusIcon(task.status)}
                      </div>
                      <div>
                        <h4 className="font-bold text-foreground uppercase">
                          {isAudit
                            ? (task.task_type === 'repository' ? '审计任务' : '即时分析任务')
                            : 'Agent 审计任务'}
                        </h4>
                        <p className="text-sm text-muted-foreground font-mono">
                          创建于 {formatDate(task.created_at)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge className={t.kind === 'agent' ? 'cyber-badge-info' : 'cyber-badge-muted'}>
                        {t.kind === 'agent' ? 'AGENT' : 'AUDIT'}
                      </Badge>
                      {getStatusBadge(task.status)}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 font-mono">
                    <div className="text-center p-3 bg-muted rounded-lg border border-border">
                      <p className="text-2xl font-bold text-foreground">{totalFiles}</p>
                      <p className="text-xs text-muted-foreground uppercase">总文件数</p>
                    </div>
                    <div className="text-center p-3 bg-muted rounded-lg border border-border">
                      <p className="text-2xl font-bold text-foreground">{totalLines}</p>
                      <p className="text-xs text-muted-foreground uppercase">代码行数</p>
                    </div>
                    <div className="text-center p-3 bg-muted rounded-lg border border-border">
                      <p className="text-2xl font-bold text-amber-400">{issuesOrFindings}</p>
                      <p className="text-xs text-muted-foreground uppercase">{isAudit ? '发现问题' : '发现漏洞'}</p>
                    </div>
                    <div className="text-center p-3 bg-muted rounded-lg border border-border">
                      <p className="text-2xl font-bold text-primary">{qualityScore.toFixed(1)}</p>
                      <p className="text-xs text-muted-foreground uppercase">质量评分</p>
                    </div>
                  </div>

                  {task.status === 'completed' && typeof qualityScore === 'number' && (
                    <div className="space-y-2 mb-4">
                      <div className="flex items-center justify-between text-sm font-mono">
                        <span className="text-muted-foreground">质量评分</span>
                        <span className="text-foreground font-bold">{qualityScore.toFixed(1)}/100</span>
                      </div>
                      <Progress value={qualityScore} className="h-2 bg-muted [&>div]:bg-primary" />
                    </div>
                  )}

                  <div className="flex justify-end space-x-2 pt-4 border-t border-border">
                    <Link to={isAudit ? `/tasks/${task.id}` : `/agent-audit/${task.id}`}>
                      <Button variant="outline" size="sm" className="cyber-btn-outline">
                        <FileText className="w-4 h-4 mr-2" />
                        查看详情
                      </Button>
                    </Link>
                  </div>
                </div>
              )})}
            </div>
          ) : (
            <div className="cyber-card p-12 text-center">
              <Activity className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-bold text-foreground mb-2 uppercase">暂无审计任务</h3>
              <p className="text-sm text-muted-foreground mb-6 font-mono">创建第一个审计任务开始代码质量分析</p>
              <Button onClick={handleCreateTask} className="cyber-btn-primary">
                <Play className="w-4 h-4 mr-2" />
                创建任务
              </Button>
            </div>
          )}
        </TabsContent>

        <TabsContent value="issues" className="flex flex-col gap-6 mt-6">
          <div className="flex items-center justify-between">
            <div className="section-header mb-0 pb-0 border-0">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <h3 className="section-title">最新发现的问题</h3>
            </div>
            {(auditTasks.length > 0 || agentTasks.length > 0) && (
              <p className="text-sm text-muted-foreground font-mono">
                已完成审计任务：{issuesSummary.completedAuditTasksCount} 次 / Agent审计：{issuesSummary.completedAgentTasksCount} 次
                {issuesSummary.isLimited ? `（各仅展示最近 ${issuesSummary.maxTasks} 次）` : ''}
                ，共 {latestProblems.length} 条问题/漏洞
              </p>
            )}
          </div>

          {loadingIssues ? (
            <div className="text-center py-12">
              <div className="loading-spinner mx-auto mb-4"></div>
              <p className="text-muted-foreground font-mono">正在加载问题列表...</p>
            </div>
          ) : latestProblems.length > 0 ? (
            <div className="space-y-4">
              {latestProblems.map((issue, index) => (
                <div key={index} className="cyber-card p-4 hover:border-border transition-all">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${issue.severity === 'critical' ? 'bg-rose-500/20 text-rose-600 dark:text-rose-400' :
                        issue.severity === 'high' ? 'bg-orange-500/20 text-orange-600 dark:text-orange-400' :
                          issue.severity === 'medium' ? 'bg-amber-500/20 text-amber-600 dark:text-amber-400' :
                            'bg-sky-500/20 text-sky-600 dark:text-sky-400'
                        }`}>
                        <AlertTriangle className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="font-bold text-base text-foreground mb-1 uppercase">{issue.title}</h4>
                        <div className="flex items-center space-x-2 text-xs text-muted-foreground font-mono">
                          <span className="bg-muted px-2 py-0.5 rounded border border-border">
                            {issue.file_path || '未知文件'}
                            {issue.line_number != null
                              ? (issue.line_end != null && issue.line_end !== issue.line_number
                                ? `:${issue.line_number}-${issue.line_end}`
                                : `:${issue.line_number}`)
                              : ''
                            }
                          </span>
                          <span>{issue.category || '-'}</span>
                          {issue.task_created_at && (
                            <span className="bg-muted px-2 py-0.5 rounded border border-border">
                              {issue.kind === 'agent' ? 'Agent' : 'Audit'} {issue.task_id?.slice(0, 8)} · {formatDate(issue.task_created_at)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Link to={issue.kind === 'agent' ? `/agent-audit/${issue.task_id}` : `/tasks/${issue.task_id}`}>
                        <Button variant="outline" size="sm" className="cyber-btn-outline">
                          <FileText className="w-4 h-4 mr-2" />
                          查看任务
                        </Button>
                      </Link>
                      <Badge className={`
                        ${issue.severity === 'critical' ? 'severity-critical' :
                          issue.severity === 'high' ? 'severity-high' :
                            issue.severity === 'medium' ? 'severity-medium' :
                              'severity-low'}
                        font-bold uppercase px-2 py-1 rounded text-xs
                      `}>
                        {issue.severity === 'critical' ? '严重' :
                          issue.severity === 'high' ? '高' :
                            issue.severity === 'medium' ? '中等' : '低'}
                      </Badge>
                    </div>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground font-mono border-t border-border pt-3">
                    {issue.description || '-'}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="cyber-card p-12 text-center">
              <CheckCircle className="w-16 h-16 text-emerald-600 dark:text-emerald-500 mx-auto mb-4" />
              <h3 className="text-lg font-bold text-foreground mb-2 uppercase">未发现问题</h3>
              <p className="text-sm text-muted-foreground font-mono">最近一次审计/Agent审计未发现明显问题，或尚未进行审计。</p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="settings" className="flex flex-col gap-6 mt-6">
          <div className="cyber-card p-6">
            <div className="section-header">
              <Edit className="w-5 h-5 text-primary" />
              <h3 className="section-title">编辑项目配置</h3>
            </div>

            <div className="flex flex-col gap-6">
              {/* 基本信息 */}
              <div className="space-y-4">
                <div>
                  <Label htmlFor="edit-name" className="font-mono font-bold uppercase text-xs text-muted-foreground">项目名称 *</Label>
                  <Input
                    id="edit-name"
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    placeholder="输入项目名称"
                    className="cyber-input mt-1"
                  />
                </div>

                <div>
                  <Label htmlFor="edit-description" className="font-mono font-bold uppercase text-xs text-muted-foreground">项目描述</Label>
                  <Textarea
                    id="edit-description"
                    value={editForm.description}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                    placeholder="输入项目描述"
                    rows={3}
                    className="cyber-input mt-1 min-h-[80px]"
                  />
                </div>
              </div>

              {/* 仓库信息 - 仅远程仓库类型显示 */}
              {editForm.source_type === 'repository' && (
                <div className="space-y-4 border-t border-border pt-4">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground flex items-center gap-2">
                    <GitBranch className="w-4 h-4" />
                    仓库信息
                  </h3>

                  <div>
                    <Label htmlFor="edit-repo-url" className="font-mono font-bold uppercase text-xs text-muted-foreground">仓库地址</Label>
                    <Input
                      id="edit-repo-url"
                      value={editForm.repository_url}
                      onChange={(e) => setEditForm({ ...editForm, repository_url: e.target.value })}
                      placeholder="https://github.com/username/repo"
                      className="cyber-input mt-1"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="edit-repo-type" className="font-mono font-bold uppercase text-xs text-muted-foreground">仓库平台</Label>
                      <Select
                        value={editForm.repository_type}
                        onValueChange={(value: any) => setEditForm({ ...editForm, repository_type: value })}
                      >
                        <SelectTrigger id="edit-repo-type" className="cyber-input mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="cyber-dialog border-border">
                          {REPOSITORY_PLATFORMS.map((platform) => (
                            <SelectItem key={platform.value} value={platform.value}>
                              {platform.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label htmlFor="edit-branch" className="font-mono font-bold uppercase text-xs text-muted-foreground">默认分支</Label>
                      <Input
                        id="edit-branch"
                        value={editForm.default_branch}
                        onChange={(e) => setEditForm({ ...editForm, default_branch: e.target.value })}
                        placeholder="main"
                        className="cyber-input mt-1"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* ZIP项目提示 */}
              {editForm.source_type === 'zip' && (
                <div className="border-t border-border pt-4">
                  <div className="bg-amber-500/10 border border-amber-500/30 p-4 rounded">
                    <div className="flex items-start space-x-3">
                      <Upload className="w-5 h-5 text-amber-400 mt-0.5" />
                      <div className="text-sm font-mono">
                        <p className="font-bold text-amber-300 mb-1 uppercase">ZIP上传项目</p>
                        <p className="text-amber-400/80 text-xs">
                          此项目通过ZIP文件上传创建。每次进行代码审计时，需要在创建任务时重新上传ZIP文件。
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* 编程语言 */}
              <div className="space-y-4 border-t border-border pt-4">
                <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground">编程语言</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {supportedLanguages.map((lang) => (
                    <div
                      key={lang}
                      className={`flex items-center space-x-2 p-3 border cursor-pointer transition-all rounded ${editForm.programming_languages?.includes(lang)
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border hover:border-border text-muted-foreground'
                        }`}
                      onClick={() => handleToggleLanguage(lang)}
                    >
                      <div
                        className={`w-4 h-4 border-2 rounded-sm flex items-center justify-center ${editForm.programming_languages?.includes(lang)
                          ? 'bg-primary border-primary'
                          : 'border-border'
                          }`}
                      >
                        {editForm.programming_languages?.includes(lang) && (
                          <CheckCircle className="w-3 h-3 text-foreground" />
                        )}
                      </div>
                      <span className="text-sm font-bold font-mono">{lang}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end space-x-3 pt-6 border-t border-border">
                <Button onClick={handleSaveSettings} className="cyber-btn-primary">
                  <Edit className="w-4 h-4 mr-2" />
                  保存修改
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>

      {/* 创建任务对话框 */}
      <CreateTaskDialog
        open={showCreateTaskDialog}
        onOpenChange={setShowCreateTaskDialog}
        onTaskCreated={handleTaskCreated}
        onFastScanStarted={handleFastScanStarted}
        preselectedProjectId={id}
      />

      {/* 终端进度对话框 */}
      <TerminalProgressDialog
        open={showTerminalDialog}
        onOpenChange={setShowTerminalDialog}
        taskId={currentTaskId}
        taskType="repository"
      />

      {/* 审计选项对话框 */}
      <Dialog open={showAuditOptionsDialog} onOpenChange={setShowAuditOptionsDialog}>
        <DialogContent className="max-w-md cyber-card border-border cyber-dialog p-0">
          {/* Terminal Header */}
          <div className="flex items-center gap-2 px-4 py-3 cyber-bg-elevated border-b border-border">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            <span className="ml-2 font-mono text-xs text-muted-foreground tracking-wider">
              audit_options@deepaudit
            </span>
          </div>

          <DialogHeader className="px-6 pt-4">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              <Shield className="w-5 h-5 text-primary" />
              选择审计方式
            </DialogTitle>
          </DialogHeader>

          <div className="p-6 space-y-4">
            <Button
              onClick={handleStartFullAudit}
              className="w-full h-auto py-4 flex flex-col items-center justify-center space-y-2 cyber-btn-outline hover:bg-muted"
            >
              <div className="flex items-center space-x-2">
                <Activity className="w-5 h-5" />
                <span className="text-lg font-bold uppercase">全量审计</span>
              </div>
              <span className="text-xs text-muted-foreground font-mono">扫描项目中的所有文件</span>
            </Button>

            <Button
              onClick={handleOpenCustomAudit}
              className="w-full h-auto py-4 flex flex-col items-center justify-center space-y-2 cyber-btn-outline hover:bg-muted"
            >
              <div className="flex items-center space-x-2">
                <FileText className="w-5 h-5" />
                <span className="text-lg font-bold uppercase">自定义审计</span>
              </div>
              <span className="text-xs text-muted-foreground font-mono">选择特定文件进行扫描</span>
            </Button>
          </div>

          <DialogFooter className="p-4 border-t border-border bg-muted/50">
            <Button variant="outline" onClick={() => setShowAuditOptionsDialog(false)} className="w-full cyber-btn-outline">
              取消
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 文件选择对话框 */}
      <FileSelectionDialog
        open={showFileSelectionDialog}
        onOpenChange={setShowFileSelectionDialog}
        projectId={id || ''}
        onConfirm={handleStartCustomAudit}
      />
    </div>
  );
}