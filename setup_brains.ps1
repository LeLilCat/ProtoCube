$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$modelsDir = Join-Path $projectRoot 'models'
$casualModelsDir = Join-Path $modelsDir 'casual'
$smartModelsDir = Join-Path $modelsDir 'smart'
$deepModelsDir = Join-Path $modelsDir 'deep'
$runtimeDir = Join-Path $projectRoot 'runtime'
$cpuDir = Join-Path $runtimeDir 'cpu'
$vulkanDir = Join-Path $runtimeDir 'vulkan'

New-Item -ItemType Directory -Force -Path $modelsDir, $casualModelsDir, $smartModelsDir, $deepModelsDir, $cpuDir, $vulkanDir | Out-Null

function Get-VerifiedFile {
    param(
        [Parameter(Mandatory)] [string] $Url,
        [Parameter(Mandatory)] [string] $Destination,
        [Parameter(Mandatory)] [long] $ExpectedSize,
        [Parameter(Mandatory)] [string] $ExpectedSha256
    )

    if (Test-Path -LiteralPath $Destination) {
        $file = Get-Item -LiteralPath $Destination
        if ($file.Length -eq $ExpectedSize -and
            (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash -eq $ExpectedSha256) {
            Write-Host "Already verified: $($file.Name)"
            return
        }
    }

    $partial = "$Destination.part"
    if (Test-Path -LiteralPath $partial) {
        $partialFile = Get-Item -LiteralPath $partial
        if ($partialFile.Length -eq $ExpectedSize -and
            (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash -eq $ExpectedSha256) {
            Move-Item -LiteralPath $partial -Destination $Destination -Force
            Write-Host "Verified completed download: $($partialFile.Name)"
            return
        }
    }
    Write-Host "Downloading $(Split-Path -Leaf $Destination)..."
    & curl.exe --fail --location --retry 5 --continue-at - --output $partial $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $Url"
    }

    $file = Get-Item -LiteralPath $partial
    if ($file.Length -ne $ExpectedSize) {
        throw "Size check failed for $($file.Name): expected $ExpectedSize, received $($file.Length)."
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $partial).Hash
    if ($actualHash -ne $ExpectedSha256) {
        throw "SHA-256 check failed for $($file.Name)."
    }
    Move-Item -LiteralPath $partial -Destination $Destination -Force
}

function Install-RuntimeArchive {
    param(
        [Parameter(Mandatory)] [string] $Url,
        [Parameter(Mandatory)] [string] $DestinationDirectory,
        [Parameter(Mandatory)] [long] $ExpectedSize,
        [Parameter(Mandatory)] [string] $ExpectedSha256
    )

    $server = Join-Path $DestinationDirectory 'llama-server.exe'
    if (Test-Path -LiteralPath $server) {
        Write-Host "Runtime already installed: $DestinationDirectory"
        return
    }

    $archive = Join-Path $DestinationDirectory 'llama-runtime.zip'
    Get-VerifiedFile -Url $Url -Destination $archive -ExpectedSize $ExpectedSize -ExpectedSha256 $ExpectedSha256

    $unpackDirectory = Join-Path $DestinationDirectory '_unpack'
    if (Test-Path -LiteralPath $unpackDirectory) {
        Remove-Item -LiteralPath $unpackDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $unpackDirectory | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $unpackDirectory -Force
    Copy-Item -Path (Join-Path $unpackDirectory '*') -Destination $DestinationDirectory -Recurse -Force
    Remove-Item -LiteralPath $unpackDirectory -Recurse -Force

    if (-not (Test-Path -LiteralPath $server)) {
        throw "Runtime archive did not contain llama-server.exe."
    }
}

function Install-DefaultModelSlot {
    param(
        [Parameter(Mandatory)] [string] $SlotDirectory,
        [Parameter(Mandatory)] [string] $DefaultFileName,
        [Parameter(Mandatory)] [string] $Url,
        [Parameter(Mandatory)] [long] $ExpectedSize,
        [Parameter(Mandatory)] [string] $ExpectedSha256
    )

    $models = @(Get-ChildItem -LiteralPath $SlotDirectory -File -Filter '*.gguf')
    if ($models.Count -gt 1) {
        throw "Keep exactly one GGUF model in $SlotDirectory before running setup."
    }

    $defaultDestination = Join-Path $SlotDirectory $DefaultFileName
    if ($models.Count -eq 1 -and $models[0].FullName -ne $defaultDestination) {
        Write-Host "Custom model preserved in $SlotDirectory`: $($models[0].Name)"
        return
    }

    Get-VerifiedFile `
        -Url $Url `
        -Destination $defaultDestination `
        -ExpectedSize $ExpectedSize `
        -ExpectedSha256 $ExpectedSha256
}

function Move-LegacyModelIntoSlot {
    param(
        [Parameter(Mandatory)] [string] $LegacyPath,
        [Parameter(Mandatory)] [string] $SlotDirectory
    )

    $slotModels = @(Get-ChildItem -LiteralPath $SlotDirectory -File -Filter '*.gguf')
    if ((Test-Path -LiteralPath $LegacyPath) -and $slotModels.Count -eq 0) {
        Move-Item -LiteralPath $LegacyPath -Destination $SlotDirectory
        Write-Host "Moved legacy model into customization slot: $SlotDirectory"
    }
}

$releaseBase = 'https://github.com/ggml-org/llama.cpp/releases/download/b10217'
Install-RuntimeArchive `
    -Url "$releaseBase/llama-b10217-bin-win-cpu-x64.zip" `
    -DestinationDirectory $cpuDir `
    -ExpectedSize 18352593 `
    -ExpectedSha256 'F60C9DCA4AE90141884757100CF4994F72AAB0FFABACCEC1344A28163189BCE8'

Install-RuntimeArchive `
    -Url "$releaseBase/llama-b10217-bin-win-vulkan-x64.zip" `
    -DestinationDirectory $vulkanDir `
    -ExpectedSize 34089052 `
    -ExpectedSha256 '957320CB0BCA241EC8249D16D4B137F0D27DF08CE7740345F36313FA21D77B2B'

Move-LegacyModelIntoSlot `
    -LegacyPath (Join-Path $modelsDir 'qwen2.5-1.5b-instruct-q5_k_m.gguf') `
    -SlotDirectory $casualModelsDir

Move-LegacyModelIntoSlot `
    -LegacyPath (Join-Path $modelsDir 'qwen2.5-3b-instruct-q4_k_m.gguf') `
    -SlotDirectory $smartModelsDir

Install-DefaultModelSlot `
    -SlotDirectory $casualModelsDir `
    -DefaultFileName 'qwen2.5-1.5b-instruct-q5_k_m.gguf' `
    -Url 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q5_k_m.gguf' `
    -ExpectedSize 1285494304 `
    -ExpectedSha256 'B46661073C18E5B56A41FA320975F866A00DEF1FF08FEEF4718E013258896F8C'

Install-DefaultModelSlot `
    -SlotDirectory $smartModelsDir `
    -DefaultFileName 'qwen2.5-3b-instruct-q4_k_m.gguf' `
    -Url 'https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf' `
    -ExpectedSize 2104932768 `
    -ExpectedSha256 '626B4A6678B86442240E33DF819E00132D3BA7DDDFE1CDC4FBB18E0A9615C62D'

Set-Content -LiteralPath (Join-Path $runtimeDir 'VERSION.txt') -Value 'llama.cpp b10217 (CPU + Vulkan x64)'
Write-Host "Deep model slot ready (no default download): $deepModelsDir"
Write-Host 'ProtoCube brain setup complete.' -ForegroundColor Green
