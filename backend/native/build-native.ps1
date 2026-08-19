<##
.SYNOPSIS
    Build the CityPulse native C++ core as a 64-bit Release DLL.
.DESCRIPTION
    I keep native compilation in one repeatable command so local development
    and CI can use the same CMake configuration.
##>

$ErrorActionPreference = "Stop"

if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake is required. Install CMake and a 64-bit C++ compiler, then rerun this script."
}

$nativePath = $PSScriptRoot
$buildPath = Join-Path $nativePath "build"

cmake -S $nativePath -B $buildPath -A x64
cmake --build $buildPath --config Release

Write-Host "Native core build completed."
