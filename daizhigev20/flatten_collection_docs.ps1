[CmdletBinding()]
param(
    [string]$CorpusRoot = $PSScriptRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$categoryNames = @('道藏', '佛藏', '集藏', '儒藏', '诗藏', '史藏', '医藏', '艺藏', '易藏', '子藏')
$rootFull = [IO.Path]::GetFullPath($CorpusRoot).TrimEnd('\')
$categories = foreach ($name in $categoryNames) {
    $path = Join-Path $rootFull $name
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "一级分类目录不存在：$path"
    }
    Get-Item -LiteralPath $path
}

$allFiles = @($categories | ForEach-Object {
    Get-ChildItem -LiteralPath $_.FullName -File -Recurse -Force
})
$nestedNonMarkdown = @($allFiles | Where-Object {
    $_.Extension -ine '.md' -and $_.DirectoryName -ne (Join-Path $rootFull $_.FullName.Substring($rootFull.Length + 1).Split('\')[0])
})
if ($nestedNonMarkdown.Count -gt 0) {
    throw "分类子目录内还有非 Markdown 文件；为避免遗漏，未开始移动：$($nestedNonMarkdown[0].FullName)"
}

$markdown = @($allFiles | Where-Object Extension -IEQ '.md')
$plan = [Collections.Generic.List[object]]::new()
foreach ($category in $categories) {
    $categoryFiles = @($markdown | Where-Object {
        $_.FullName.StartsWith($category.FullName.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
    })
    foreach ($group in @($categoryFiles | Group-Object Name)) {
        foreach ($file in $group.Group) {
            $suffix = ''
            if ($group.Count -gt 1) {
                $relativeDirectory = $file.DirectoryName.Substring($category.FullName.TrimEnd('\').Length).TrimStart('\')
                $segments = @($relativeDirectory -split '\\' | Where-Object { $_ })
                if ($segments.Count -eq 0) { $suffix = '原根目录' }
                else { $suffix = $segments[0] }
            }

            $destinationName = if ($suffix) {
                '{0}（{1}）{2}' -f $file.BaseName, $suffix, $file.Extension
            } else {
                $file.Name
            }
            $destination = Join-Path $category.FullName $destinationName
            $plan.Add([pscustomobject]@{
                Source = $file.FullName
                Destination = $destination
                RelativeSource = $file.FullName.Substring($rootFull.Length + 1)
                Category = $category.Name
                Suffix = $suffix
            })
        }
    }
}

$destinations = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($item in $plan) {
    $destination = [IO.Path]::GetFullPath($item.Destination)
    $categoryRoot = [IO.Path]::GetFullPath((Join-Path $rootFull $item.Category)).TrimEnd('\') + '\'
    if (-not $destination.StartsWith($categoryRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "目标路径越界：$destination"
    }
    if (-not $destinations.Add($destination)) {
        throw "自动加后缀后仍有重名，未开始移动：$destination"
    }
    if ((Test-Path -LiteralPath $destination -PathType Leaf) -and
        -not [string]::Equals($destination, [IO.Path]::GetFullPath($item.Source), [StringComparison]::OrdinalIgnoreCase)) {
        throw "目标文件已存在，未开始移动：$destination"
    }
}

$moves = @($plan | Where-Object {
    -not [string]::Equals([IO.Path]::GetFullPath($_.Source), [IO.Path]::GetFullPath($_.Destination), [StringComparison]::OrdinalIgnoreCase)
})
$moved = [Collections.Generic.List[object]]::new()
try {
    foreach ($item in $moves) {
        Move-Item -LiteralPath $item.Source -Destination $item.Destination
        $moved.Add($item)
    }
} catch {
    for ($i = $moved.Count - 1; $i -ge 0; $i--) {
        $item = $moved[$i]
        if (Test-Path -LiteralPath $item.Destination -PathType Leaf) {
            Move-Item -LiteralPath $item.Destination -Destination $item.Source
        }
    }
    throw "移动失败，已尝试恢复刚才移动的文件：$($_.Exception.Message)"
}

$removedDirectories = 0
foreach ($category in $categories) {
    $subdirectories = @(Get-ChildItem -LiteralPath $category.FullName -Directory -Recurse -Force |
        Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $subdirectories) {
        if (@(Get-ChildItem -LiteralPath $directory.FullName -Force).Count -eq 0) {
            Remove-Item -LiteralPath $directory.FullName
            $removedDirectories++
        }
    }
}

$remainingDirectories = @($categories | ForEach-Object {
    Get-ChildItem -LiteralPath $_.FullName -Directory -Recurse -Force
})
if ($remainingDirectories.Count -gt 0) {
    throw "仍有未清理的二级目录：$($remainingDirectories[0].FullName)"
}

Write-Output "一级藏目录：$($categories.Count)"
Write-Output "古籍 Markdown：$($markdown.Count)"
Write-Output "移动或改名：$($moves.Count)"
Write-Output "重名文件加后缀：$(@($plan | Where-Object Suffix).Count)"
Write-Output "清除的空子目录：$removedDirectories"
Write-Output '重名文件处理：仅在同一藏内重名时，文件名加原子目录名括号后缀；正文不改。'
