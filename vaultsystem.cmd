@echo off
setlocal
powershell.exe -NoLogo -NoProfile -Command ^
  "$logo = @('    .--------.', '   /  o    o  \--o', '  |    \  /    |', '  |     @------+--o', '  |    /  \    |', '   \  o    o  /--o', '    ''--------''');" ^
  "$server = if ($env:VS_URL) { $env:VS_URL } else { '(nao configurado)' };" ^
  "$session = if ($env:VS_TOKEN) { 'token no ambiente' } else { 'sem token' };" ^
  "$info = @('Vault System  [VS CLI]', 'Conhecimento distribuido.', '', 'versao    previa local', ('servidor  ' + $server), ('sessao    ' + $session), '');" ^
  "$width = ($info | Measure-Object -Property Length -Maximum).Maximum;" ^
  "$logoWidth = ($logo | Measure-Object -Property Length -Maximum).Maximum + 3;" ^
  "$edge = '+' + ('-' * ($logoWidth + $width + 4)) + '+';" ^
  "Write-Host $edge -ForegroundColor DarkBlue;" ^
  "for ($i = 0; $i -lt $logo.Count; $i++) { Write-Host '|  ' -NoNewline -ForegroundColor DarkBlue; Write-Host ($logo[$i].PadRight($logoWidth)) -NoNewline -ForegroundColor Cyan; $color = if ($i -eq 0) {'Cyan'} else {'Gray'}; Write-Host ($info[$i].PadRight($width) + '  ') -NoNewline -ForegroundColor $color; Write-Host '|' -ForegroundColor DarkBlue };" ^
  "Write-Host $edge -ForegroundColor DarkBlue; Write-Host ''; Write-Host '  Para comecar  [comandos da previa]' -ForegroundColor Cyan;" ^
  "@('vs login', 'vs init', 'vs add template docker:python', 'vs ajuda') | ForEach-Object { Write-Host ('    > ' + $_) }"
exit /b %errorlevel%
