[CmdletBinding()]
param(
    [ValidateSet('Summary', 'Matrix', 'Candidates', 'All')]
    [string]$Mode = 'All',
    [string]$CorpusRoot = $PSScriptRoot,
    [string]$WangRoot = 'D:\26大创\04-项目文献\A-原著原典',
    [switch]$IncludeWeak
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Read-only audit. This script never deletes, moves, rewrites, or imports corpus files.

$wangFiles = @(
    @{ Name = '读书杂志_王念孙'; Path = (Join-Path $WangRoot '读书杂志_王念孙.md') },
    @{ Name = '广雅疏证_王念孙'; Path = (Join-Path $WangRoot '广雅疏证_王念孙.md') },
    @{ Name = '经传释词_王引之'; Path = (Join-Path $WangRoot '经传释词_王引之.md') },
    @{ Name = '经义述闻_王引之'; Path = (Join-Path $WangRoot '经义述闻_王引之.md') }
)

$traditionalMap = @{
    '説'='说'; '說'='说'; '廣'='广'; '爾'='尔'; '眾'='众'; '衆'='众'; '經'='经'; '義'='义';
    '傳'='传'; '書'='书'; '禮'='礼'; '學'='学'; '醫'='医'; '藥'='药'; '黃'='黄'; '國'='国';
    '漢'='汉'; '後'='后'; '與'='与'; '為'='为'; '爲'='为'; '臺'='台'; '從'='从'; '於'='于';
    '見'='见'; '會'='会'; '寶'='宝'; '圖'='图'; '氣'='气'; '標'='标'; '體'='体'; '聲'='声';
    '關'='关'; '聞'='闻'; '別'='别'; '錄'='录'; '録'='录'; '點'='点'; '號'='号'; '劉'='刘';
    '華'='华'; '龍'='龙'; '門'='门'; '東'='东'; '車'='车'; '馬'='马'; '鳥'='鸟'; '魚'='鱼';
    '獸'='兽'; '蟲'='虫'; '風'='风'; '雲'='云'; '異'='异'; '詞'='词'; '釋'='释'; '辭'='辞';
    '類'='类'; '續'='续'; '補'='补'; '訓'='训'; '詁'='诂'; '證'='证'; '箋'='笺'; '記'='记';
    '覽'='览'; '羣'='群'; '晉'='晋'; '韓'='韩'; '齊'='齐'; '趙'='赵'; '藝'='艺'; '倉'='仓';
    '頡'='颉'; '選'='选'; '樂'='乐'; '內'='内'; '喪'='丧'; '穀'='谷'; '數'='数'; '堯'='尧';
    '貢'='贡'; '緇'='缁'; '雜'='杂'; '繫'='系'; '鴻'='鸿'; '術'='术'; '農'='农'; '齋'='斋';
    '賦'='赋'; '紀'='纪'; '韻'='韵'; '館'='馆'; '詩'='诗'; '論'='论'; '莊'='庄'; '賈'='贾';
    '鈔'='钞'; '問'='问'; '開'='开'; '占'='占'; '縣'='县'; '濟'='济'; '榮'='荣'; '條'='条';
    '敘'='叙'; '獨'='独'; '衛'='卫'; '師'='师'; '軍'='军'; '無'='无'
}

function Convert-Compact([string]$Text) {
    $normalized = $Text.Normalize([Text.NormalizationForm]::FormKC)
    $builder = [Text.StringBuilder]::new()
    foreach ($character in $normalized.ToCharArray()) {
        $charText = [string]$character
        if ($traditionalMap.ContainsKey($charText)) {
            [void]$builder.Append($traditionalMap[$charText])
        }
        else {
            [void]$builder.Append($charText.ToLowerInvariant())
        }
    }
    return [regex]::Replace($builder.ToString(), '[\s_\-—–·•．・/\\、，,。:：;；（）()【】\[\]<>〈〉《》“”"''‘’]', '')
}

function Get-QueryAliases([string]$Stem) {
    $aliases = [Collections.Generic.HashSet[string]]::new()
    [void]$aliases.Add((Convert-Compact $Stem))

    $main = [regex]::Replace($Stem, '[_（(].*$', '')
    $main = [regex]::Replace($main, '[-—].*$', '')
    if ($main) { [void]$aliases.Add((Convert-Compact $main)) }

    if ($main.StartsWith('春秋') -and $main.Length -ge 4) { [void]$aliases.Add((Convert-Compact $main.Substring(2))) }
    if ($main.StartsWith('重修') -and $main.Length -ge 4) { [void]$aliases.Add((Convert-Compact $main.Substring(2))) }
    if ($main.StartsWith('原本') -and $main.Length -ge 4) { [void]$aliases.Add((Convert-Compact $main.Substring(2))) }
    if ($main.StartsWith('续') -and $main.Length -ge 4) { [void]$aliases.Add((Convert-Compact $main.Substring(1))) }

    foreach ($suffix in @('注疏','集解','索隐','正义','校注','校箋','校笺','补注','集释','补遗','释文','补','解','注','疏','传','翼')) {
        if ($main.EndsWith($suffix) -and $main.Length - $suffix.Length -ge 3) {
            [void]$aliases.Add((Convert-Compact $main.Substring(0, $main.Length - $suffix.Length)))
        }
    }

    $manual = @{
        '说文解字'=@('说文'); '说文解字注'=@('说文'); '尔雅注'=@('尔雅'); '尔雅注疏'=@('尔雅');
        '尔雅翼'=@('尔雅'); '广雅疏证'=@('广雅'); '重修玉篇'=@('玉篇'); '原本广韵'=@('广韵');
        '重修广韵'=@('广韵'); '黄帝内经素问'=@('素问'); '重广补注黄帝内经素问'=@('素问');
        '神农本草经'=@('神农本草'); '神农本草经疏'=@('神农本草'); '经典释文'=@('释文');
        '续一切经音义'=@('一切经音义'); '春秋左传'=@('左传'); '春秋公羊传'=@('公羊传');
        '春秋谷梁传'=@('谷梁传'); '春秋穀梁传'=@('谷梁传'); '群书治要六韬'=@('群书治要');
        '文选注'=@('文选'); '六臣注文选'=@('文选'); '大戴礼记'=@('大戴礼');
        '太平御览道部'=@('太平御览'); '晏子春秋集释'=@('晏子春秋'); '孔子家语'=@('家语')
    }
    if ($manual.ContainsKey($main)) {
        foreach ($alias in $manual[$main]) { [void]$aliases.Add((Convert-Compact $alias)) }
    }
    return @($aliases | Where-Object { $_ })
}

$weakAliases = @('序','传','注','疏','志','书','礼','易','诗','史','文','集','本','记','论','说','卷','篇','部','目录','校','补') |
    ForEach-Object { Convert-Compact $_ }

$mdFiles = @(Get-ChildItem -LiteralPath $CorpusRoot -Recurse -Force -File | Where-Object { $_.Extension -ieq '.md' })
$records = [Collections.Generic.List[object]]::new()
$recordByPath = @{}
$exactIndex = @{}
$aliasIndex = @{}

foreach ($file in $mdFiles) {
    $relative = $file.FullName.Substring($CorpusRoot.Length).TrimStart('\','/')
    $parts = $relative -split '[\\/]'
    # Parenthetical suffixes added to distinguish same-named flat files are
    # provenance labels, not part of the work title used for citation matching.
    $canonicalStem = [regex]::Replace($file.BaseName, '（[^（）]*）$', '')
    $record = [pscustomobject]@{
        RelativePath = $relative
        Stem = $file.BaseName
        Top = if ($parts.Count -ge 1) { $parts[0] } else { '' }
        Second = if ($parts.Count -ge 3) { $parts[1] } else { '' }
        ExactStem = Convert-Compact $canonicalStem
        Aliases = @(Get-QueryAliases $file.BaseName)
        ExactHits = 0
        FamilyHits = 0
        WeakHits = 0
        Works = [Collections.Generic.HashSet[string]]::new()
        Examples = [Collections.Generic.List[string]]::new()
    }
    $records.Add($record)
    $recordByPath[$relative] = $record

    if (-not $exactIndex.ContainsKey($record.ExactStem)) { $exactIndex[$record.ExactStem] = [Collections.Generic.List[object]]::new() }
    $exactIndex[$record.ExactStem].Add($record)
    foreach ($alias in $record.Aliases) {
        if (-not $aliasIndex.ContainsKey($alias)) { $aliasIndex[$alias] = [Collections.Generic.List[object]]::new() }
        $aliasIndex[$alias].Add($record)
    }
}

function Get-CitationForms([string]$Inner) {
    $clean = [regex]::Replace($Inner, '\s+', '').Trim()
    $forms = [Collections.Generic.HashSet[string]]::new()
    [void]$forms.Add((Convert-Compact $clean))
    foreach ($separator in @('·','•','．','・',':','：')) {
        if ($clean.Contains($separator)) {
            $pieces = $clean -split [regex]::Escape($separator)
            foreach ($piece in $pieces) { if ($piece) { [void]$forms.Add((Convert-Compact $piece)) } }
            [void]$forms.Add((Convert-Compact ($clean.Split($separator)[0])))
        }
    }
    return @($forms | Where-Object { $_ })
}

foreach ($wang in $wangFiles) {
    if (-not (Test-Path -LiteralPath $wang.Path -PathType Leaf)) { throw "王氏文件不存在: $($wang.Path)" }
    $lineNo = 0
    foreach ($line in Get-Content -LiteralPath $wang.Path -Encoding UTF8) {
        $lineNo++
        foreach ($match in [regex]::Matches($line, '[《〈](.{1,120}?)[》〉]')) {
            $inner = $match.Groups[1].Value
            $forms = @(Get-CitationForms $inner)
            $eventMatches = @{}

            foreach ($form in $forms) {
                for ($length = 1; $length -le $form.Length; $length++) {
                    $prefix = $form.Substring(0, $length)
                    if ($aliasIndex.ContainsKey($prefix)) {
                        foreach ($record in $aliasIndex[$prefix]) {
                            if (-not $eventMatches.ContainsKey($record.RelativePath)) { $eventMatches[$record.RelativePath] = [Collections.Generic.HashSet[string]]::new() }
                            [void]$eventMatches[$record.RelativePath].Add($prefix)
                        }
                    }
                }
            }

            foreach ($relativePath in $eventMatches.Keys) {
                $record = $recordByPath[$relativePath]
                $matchedAliases = @($eventMatches[$relativePath])
                $bestAlias = $matchedAliases | Sort-Object Length -Descending | Select-Object -First 1
                $isExact = $forms -contains $record.ExactStem
                $isWeak = $weakAliases -contains $bestAlias -or $bestAlias.Length -lt 3
                if ($isExact) { $record.ExactHits++ }
                elseif ($isWeak) { $record.WeakHits++ }
                else { $record.FamilyHits++ }
                [void]$record.Works.Add($wang.Name)
                if ($record.Examples.Count -lt 3 -and -not $isWeak) {
                    $record.Examples.Add("$($wang.Name):${lineNo}:$inner")
                }
            }
        }
    }
}

$strong = @($records | Where-Object { $_.ExactHits -gt 0 -or $_.FamilyHits -gt 0 })
$exactStrong = @($records | Where-Object { $_.ExactHits -gt 0 -and $_.ExactStem.Length -ge 3 -and ($weakAliases -notcontains $_.ExactStem) })
$weakOnly = @($records | Where-Object { $_.ExactHits -eq 0 -and $_.FamilyHits -eq 0 -and $_.WeakHits -gt 0 })

Write-Output '=== AUDIT_WANG_QUERY_READ_ONLY ==='
Write-Output "corpus_root`t$CorpusRoot"
Write-Output "markdown_files`t$($records.Count)"
Write-Output "strict_exact_strong_files`t$($exactStrong.Count)"
Write-Output "strong_exact_or_family_files`t$($strong.Count)"
Write-Output "weak_only_files`t$($weakOnly.Count)"
Write-Output 'note`tweak matches such as 序/传/注 are not treated as academic title hits'

if ($Mode -in @('Candidates','All')) {
    Write-Output "`n=== DIRECTORY_CANDIDATES ==="
    $groups = @{}
    foreach ($record in $records) {
        $key = if ($record.Second) { "$($record.Top)\$($record.Second)" } else { $record.Top }
        if (-not $groups.ContainsKey($key)) { $groups[$key] = [Collections.Generic.List[object]]::new() }
        $groups[$key].Add($record)
    }
    foreach ($key in ($groups.Keys | Sort-Object)) {
        $group = @($groups[$key])
        $groupStrong = @($group | Where-Object { $_.ExactHits -gt 0 -or $_.FamilyHits -gt 0 })
        $status = if ($groupStrong.Count -eq 0) { 'DELETE_CANDIDATE' } else { 'PARTIAL_DELETE_CANDIDATE' }
        $sample = ($group | Where-Object { $_.ExactHits -eq 0 -and $_.FamilyHits -eq 0 } | Select-Object -First 3 | ForEach-Object RelativePath) -join ' | '
        Write-Output "$status`t$key`ttotal=$($group.Count)`tstrong=$($groupStrong.Count)`tweak=$(@($group | Where-Object WeakHits -gt 0).Count)`tsample=$sample"
    }
}

if ($Mode -in @('Matrix','All')) {
    Write-Output "`n=== FILE_MATRIX_TSV ==="
    Write-Output 'status`tpath`texact_hits`tfamily_hits`tweak_hits`tworks`texamples'
    foreach ($record in ($records | Sort-Object RelativePath)) {
        $status = if ($record.ExactHits -gt 0 -or $record.FamilyHits -gt 0) { 'STRONG' } elseif ($record.WeakHits -gt 0) { 'WEAK_ONLY' } else { 'NO_HIT' }
        $works = ($record.Works | Sort-Object) -join ','
        $examples = ($record.Examples -join ' | ') -replace "`t", ' '
        Write-Output "$status`t$($record.RelativePath)`t$($record.ExactHits)`t$($record.FamilyHits)`t$($record.WeakHits)`t$works`t$examples"
    }
}
