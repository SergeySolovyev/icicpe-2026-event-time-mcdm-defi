[CmdletBinding()]
param(
    [switch]$Deploy,
    [ValidatePattern('^[a-z0-9][a-z0-9-]*$')]
    [string]$SubgraphName = 'mirage-morpho-markets',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$VersionLabel = 'v0.0.1'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$nodeExe = (Get-Command node -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$graphCli = Join-Path $PSScriptRoot 'node_modules\@graphprotocol\graph-cli\bin\run.js'
if (-not (Test-Path -LiteralPath $graphCli -PathType Leaf)) {
    throw 'Dependencies are missing. Run npm ci in subgraph/ first.'
}
if ($Deploy -and [string]::IsNullOrWhiteSpace($env:MIRAGE_GRAPH_DEPLOY_KEY)) {
    throw 'Set MIRAGE_GRAPH_DEPLOY_KEY in this terminal session before deploying. Do not put it in a file or command argument.'
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $manifestPath = Join-Path $PSScriptRoot 'subgraph.yaml'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
    $requiredEvent = 'CreateMarket(indexed bytes32,(address,address,address,address,uint256))'
    if (-not $manifest.Contains($requiredEvent) -or
        ([regex]::Matches($manifest, '(?m)^\s*- event:').Count -ne 1)) {
        throw 'Expected exactly one CreateMarket handler with the verified tuple signature.'
    }
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash

    Write-Host 'Generating types with the pinned Graph CLI...'
    & $nodeExe $graphCli codegen --skip-migrations
    if ($LASTEXITCODE -ne 0) { throw "Graph codegen failed (exit $LASTEXITCODE)." }
    Write-Host 'Building the discovery subgraph...'
    & $nodeExe $graphCli build --skip-migrations
    if ($LASTEXITCODE -ne 0) { throw "Graph build failed (exit $LASTEXITCODE)." }
    if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne $manifestHash) {
        throw 'The manifest changed during preparation. Review it before deployment.'
    }

    if (-not $Deploy) {
        Write-Host 'Local preparation passed. To deploy to Studio, run this script with -Deploy.'
        return
    }

    # Construct CLI arguments in Node memory: the key is never an OS command-line
    # argument and graph auth does not write it into ~/.graph-cli.json.
    $deployCode = @'
delete process.env.DEBUG;
const key = process.env.MIRAGE_GRAPH_DEPLOY_KEY;
delete process.env.MIRAGE_GRAPH_DEPLOY_KEY;
if (!key || !key.trim()) {
  process.stderr.write("MIRAGE_GRAPH_DEPLOY_KEY is missing.\n");
  process.exit(1);
}
const { pathToFileURL } = await import("node:url");
const path = await import("node:path");
const { execute } = await import("@oclif/core");
const [name, version] = process.argv.slice(1);
await execute({
  dir: pathToFileURL(path.resolve("node_modules/@graphprotocol/graph-cli/bin/run.js")).href,
  args: ["deploy", name, "--node", "https://api.studio.thegraph.com/deploy/",
    "--deploy-key", key, "--version-label", version, "--skip-migrations"]
});
'@
    Write-Host "Deploying $SubgraphName ($VersionLabel) to Subgraph Studio..."
    & $nodeExe --input-type=module --eval $deployCode $SubgraphName $VersionLabel
    if ($LASTEXITCODE -ne 0) { throw "Studio deployment failed (exit $LASTEXITCODE)." }
    Write-Host 'Deployment request completed. Verify synchronization and query real entities in Studio.'
}
finally {
    Pop-Location
}
