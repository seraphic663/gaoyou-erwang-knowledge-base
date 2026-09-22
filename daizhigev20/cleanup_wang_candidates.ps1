[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$CorpusRoot = $PSScriptRoot,
    [string]$AuditScript = (Join-Path $PSScriptRoot 'audit_wang_query.ps1')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# This cleanup is intentionally narrower than "delete every non-match":
# - whole directories listed below were DELETE_CANDIDATE in the latest scan;
# - files inside partial directories are deleted only when status is NO_HIT;
# - WEAK_ONLY and STRONG files are preserved;
# - deletion is sent to the Windows Recycle Bin.

$wholeDirectories = @(
    '道藏\正统道藏洞神部',
    '道藏\正统道藏洞玄部',
    '道藏\正统道藏太平部',
    '佛藏\嘉兴藏',
    '集藏\宝卷',
    '集藏\四库别集',
    '儒藏\修身治家',
    '诗藏\词话',
    '诗藏\词集',
    '诗藏\对联',
    '诗藏\剧曲',
    '诗藏\诗话',
    '诗藏\诗集',
    '史藏\纪事本末',
    '史藏\经世文编',
    '史藏\诏令奏议',
    '医藏\古今图书集成博物汇编艺术典医部全录',
    '艺藏\草木鸟兽虫鱼',
    '艺藏\绘画',
    '艺藏\竞技',
    '艺藏\棋技',
    '艺藏\武术',
    '艺藏\篆刻',
    '艺藏\综合'
)

$partialDirectories = @(
    '道藏\正统道藏洞真部', '道藏\正统道藏太玄部', '道藏\正统道藏续道藏', '道藏\正统道藏正一部',
    '佛藏\藏外', '佛藏\大藏经', '佛藏\乾隆藏', '佛藏\续藏经',
    '集藏\文评', '集藏\文总集',
    '儒藏\春秋', '儒藏\乐经', '儒藏\礼经', '儒藏\启蒙蒙学', '儒藏\尚书', '儒藏\诗经',
    '儒藏\四书', '儒藏\五经总义', '儒藏\小学', '儒藏\孝经', '儒藏\语录',
    '诗藏\楚辞', '诗藏\汉赋',
    '史藏\编年', '史藏\别史', '史藏\传记', '史藏\地理', '史藏\目录', '史藏\史评',
    '史藏\载记', '史藏\正史', '史藏\政书', '史藏\职官', '史藏\志存记录',
    '医藏',
    '艺藏\书法', '艺藏\饮馔',
    '易藏\术数', '易藏\易经',
    '子藏\笔记', '子藏\兵家', '子藏\法家', '子藏\类书', '子藏\农家', '子藏\算法', '子藏\诸子'
)

$protectedNames = @('README.md', 'FONTS.md', 'audit_wang_query.ps1', 'cleanup_wang_candidates.ps1')
$protectedPrefixes = @('.sources\')

if (-not (Test-Path -LiteralPath $AuditScript -PathType Leaf)) { throw "审计脚本不存在: $AuditScript" }

$matrixLines = @(& pwsh.exe -NoProfile -NonInteractive -File $AuditScript -Mode Matrix)
$noHit = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($line in $matrixLines) {
    if (-not $line.StartsWith('NO_HIT' + "`t")) { continue }
    $columns = $line -split "`t", 7
    if ($columns.Count -ge 2) { [void]$noHit.Add($columns[1]) }
}

$directoryTargets = [Collections.Generic.List[string]]::new()
foreach ($relative in $wholeDirectories) {
    $full = Join-Path $CorpusRoot $relative
    if (Test-Path -LiteralPath $full -PathType Container) { $directoryTargets.Add($relative) }
}

$fileTargets = [Collections.Generic.List[string]]::new()
foreach ($relative in $noHit) {
    if ($protectedNames -contains ([IO.Path]::GetFileName($relative))) { continue }
    if ($protectedPrefixes | Where-Object { $relative.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }) { continue }
    $isPartial = $false
    foreach ($partial in $partialDirectories) {
        $prefix = $partial.TrimEnd('\') + '\'
        if ($relative.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { $isPartial = $true; break }
    }
    if ($isPartial) { $fileTargets.Add($relative) }
}

# Do not separately delete files already covered by a whole-directory target.
$fileTargets = @($fileTargets | Where-Object {
    $path = $_
    -not ($directoryTargets | Where-Object { $path.StartsWith($_.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) })
})

Write-Output '=== CLEANUP_PLAN_READ_ONLY ==='
Write-Output "whole_directories=$($directoryTargets.Count)"
Write-Output "individual_no_hit_files=$($fileTargets.Count)"
Write-Output "total_directory_entries=$($directoryTargets.Count + $fileTargets.Count)"
Write-Output 'mode=' + $(if ($Execute) { 'EXECUTE_TO_RECYCLE_BIN' } else { 'DRY_RUN' })

foreach ($relative in $directoryTargets) { Write-Output "DIR`t$relative" }
foreach ($relative in ($fileTargets | Sort-Object)) { Write-Output "FILE`t$relative" }

if (-not $Execute) { return }

Add-Type -AssemblyName Microsoft.VisualBasic
$ui = [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs
$recycle = [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
$deleted = 0
$failed = 0

foreach ($relative in $directoryTargets) {
    $full = Join-Path $CorpusRoot $relative
    try {
        if (Test-Path -LiteralPath $full -PathType Container) {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($full, $ui, $recycle)
            $deleted++
        }
    }
    catch {
        $failed++
        Write-Error "删除目录失败: $relative :: $($_.Exception.Message)"
    }
}

foreach ($relative in ($fileTargets | Sort-Object)) {
    $full = Join-Path $CorpusRoot $relative
    try {
        if (Test-Path -LiteralPath $full -PathType Leaf) {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($full, $ui, $recycle)
            $deleted++
        }
    }
    catch {
        $failed++
        Write-Error "删除文件失败: $relative :: $($_.Exception.Message)"
    }
}

Write-Output "deleted_to_recycle_bin=$deleted"
Write-Output "failed=$failed"
