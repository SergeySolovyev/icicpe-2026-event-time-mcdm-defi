$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$assetDir = $PSScriptRoot
$paper = [Drawing.ColorTranslator]::FromHtml('#f3f2eb')
$ink = [Drawing.ColorTranslator]::FromHtml('#172f35')
$muted = [Drawing.ColorTranslator]::FromHtml('#64767a')
$aqua = [Drawing.ColorTranslator]::FromHtml('#6ee2ca')
$line = [Drawing.ColorTranslator]::FromHtml('#dcded6')
function New-Canvas([int]$width, [int]$height) {
    $bitmap = [Drawing.Bitmap]::new($width, $height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear($paper)
    return @($bitmap, $graphics)
}
function Draw-Word([Drawing.Graphics]$graphics, [string]$text, [single]$x, [single]$y, [single]$size, [Drawing.Color]$color, [string]$fontName = 'Bahnschrift') {
    $font = [Drawing.Font]::new($fontName, $size, [Drawing.FontStyle]::Regular, [Drawing.GraphicsUnit]::Pixel)
    $brush = [Drawing.SolidBrush]::new($color)
    $graphics.DrawString($text, $font, $brush, $x, $y)
    $brush.Dispose(); $font.Dispose()
}
function Draw-Mark([Drawing.Graphics]$graphics, [single]$x, [single]$y, [single]$scale) {
    # Exact brand paths from mirage/web/index.html (35 x 30 viewBox).
    $pen = [Drawing.Pen]::new($ink, [single](1.6 * $scale))
    $pen.StartCap = [Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [Drawing.Drawing2D.LineCap]::Round
    $pen.LineJoin = [Drawing.Drawing2D.LineJoin]::Round
    foreach ($segment in @(@(1,24,10,5),@(10,5,18,24),@(17,24,25,5),@(25,5,34,24),@(5,16,13,16),@(22,16,30,16))) {
        $graphics.DrawLine($pen, [single]($x+$segment[0]*$scale), [single]($y+$segment[1]*$scale), [single]($x+$segment[2]*$scale), [single]($y+$segment[3]*$scale))
    }
    $pen.Dispose()
}
$logo = New-Canvas 512 512
Draw-Mark $logo[1] 91 83 9.4
Draw-Word $logo[1] 'MIRAGE' 117 363 63 $ink
$logo[0].Save((Join-Path $assetDir 'mirage-logo-512.png'), [Drawing.Imaging.ImageFormat]::Png)
$logo[1].Dispose(); $logo[0].Dispose()

$cover = New-Canvas 1600 900
$g = $cover[1]
Draw-Mark $g 83 65 2.8
Draw-Word $g 'MIRAGE' 204 69 54 $ink
Draw-Word $g 'ETHONLINE 2026  /  CONTINUITY' 1035 87 23 $muted
$rule = [Drawing.Pen]::new($line, 2)
$g.DrawLine($rule, 88, 177, 1512, 177)
Draw-Word $g 'Before the yield,' 82 225 100 $ink 'Georgia'
Draw-Word $g 'check the evidence.' 82 335 100 $ink 'Georgia'
Draw-Word $g 'Evidence before allocation in Morpho Blue lending markets.' 91 483 31 $muted
$cards = @(@('01','Oracle observations'),@('02','Accounting consistency'),@('03','Uniswap exit quotes'))
$cardBrush = [Drawing.SolidBrush]::new([Drawing.ColorTranslator]::FromHtml('#e7eee6'))
for ($i=0; $i -lt 3; $i++) {
    $x = 88 + $i * 487
    $g.FillRectangle($cardBrush, $x, 617, 450, 139)
    Draw-Word $g $cards[$i][0] ($x+23) 637 21 $muted
    Draw-Word $g $cards[$i][1] ($x+23) 687 29 $ink
}
Draw-Word $g 'ETHEREUM  /  THE GRAPH  /  UNISWAP V3' 90 816 24 $muted
$cover[0].Save((Join-Path $assetDir 'mirage-cover-1600x900.png'), [Drawing.Imaging.ImageFormat]::Png)
$cardBrush.Dispose(); $rule.Dispose(); $g.Dispose(); $cover[0].Dispose()
Get-Item -LiteralPath (Join-Path $assetDir 'mirage-logo-512.png'), (Join-Path $assetDir 'mirage-cover-1600x900.png') | Select-Object Name, Length
