#requires -Version 5.1
[CmdletBinding()]param([switch]$SelfTest,[switch]$PublicPreflight,[switch]$VerifyOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$src='SupraCraft/VanillaCord-private';$dst='SupraCraft/VanillaCord';$tag='v2.9.0'
$jar='supracraft-vanillacord-2.9.0.jar';$size=2457878
$sha='24e850a261dbf108e2f7ac412c34651ffae753543665ec47d5e40ff9c8981719'
$origin='3d81d535ef3664c19a909ca7428ef84a778834c4'
$url="https://github.com/$dst/releases/download/$tag/$jar"
$script:gh='';$script:stage='start'
function Check([bool]$b,[string]$why){if(-not $b){throw "VC290_STOP [$script:stage]: $why"}}
function PublicJson([string]$uri,[bool]$optional=$false){
 try{$v=Invoke-RestMethod -Uri $uri -UseBasicParsing -TimeoutSec 40 -Headers @{'User-Agent'='SupraCraft-VC290';'Accept'='application/vnd.github+json'}
 if($v -is [string]){return ConvertFrom-Json -InputObject $v};return $v}
 catch{$status=0;if($null -ne $_.Exception.Response){try{$status=[int]$_.Exception.Response.StatusCode}catch{}}
 if($optional -and $status -eq 404){return $null};throw "VC290_STOP [$script:stage]: HTTP $status at $uri"}
}
function Gh([string[]]$args){
 $old=$ErrorActionPreference
 try{$ErrorActionPreference='Continue';$lines=@(& $script:gh @args);$code=$LASTEXITCODE}
 finally{$ErrorActionPreference=$old}
 Check ($code -eq 0) "GitHub CLI $($args[0]) returned exit $code"
 return ([string]::Join([Environment]::NewLine,[string[]]$lines)).Trim()
}
function GhJson([string]$path){return ConvertFrom-Json -InputObject (Gh @('api',$path))}
function SourceProof($r,$t){
 Check ([long]$r.id -eq 379240422 -and $r.tag_name -eq $tag -and $r.draft -eq $false) 'Original private release drift'
 Check ($r.target_commitish -eq $origin -and $t.object.type -eq 'commit' -and $t.object.sha -eq $origin) 'Original private tag/commit drift'
 $found=@($r.assets|Where-Object{[long]$_.id -eq 536430211 -and $_.name -eq $jar -and [long]$_.size -eq $size -and $_.digest -eq "sha256:$sha" -and $_.state -eq 'uploaded'})
 Check ($found.Count -eq 1) 'Original private JAR identity/digest drift'
}
function JarProof([string]$path,[string]$kind){
 Check (Test-Path -LiteralPath $path -PathType Leaf) "$kind JAR missing"
 Check ((Get-Item -LiteralPath $path).Length -eq $size) "$kind size differs"
 Check ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $sha) "$kind SHA256 differs"
 Write-Host "VC290_$($kind)_PASS: sha256:$sha"
}
function Head(){
 $v=(PublicJson "https://api.github.com/repos/$dst/git/ref/heads/main").object.sha
 Check ($v -match '^[a-f0-9]{40}$') 'Public HEAD missing';return $v
}
function State(){return @{Release=(PublicJson "https://api.github.com/repos/$dst/releases/tags/$tag" $true);Tag=(PublicJson "https://api.github.com/repos/$dst/git/ref/tags/$tag" $true)}}
function Manifest([string]$commit){
 $m=PublicJson "https://raw.githubusercontent.com/$dst/$commit/STABLE_RELEASE.json"
 Check ($m.tag -eq $tag -and $m.version -eq '2.9.0') 'Public manifest version differs'
 Check ($m.artifact.name -eq $jar -and $m.artifact.sha256 -eq $sha -and $m.artifact.download_url -eq $url) 'Public manifest artifact differs'
}
function PublicProof($p,[string]$commit,[string]$tmp){
 Check ($null -ne $p.Release -and $null -ne $p.Tag) 'Public release/tag incomplete'
 Check ($p.Release.tag_name -eq $tag -and $p.Release.draft -eq $false) 'Public release identity differs'
 Check ($p.Tag.object.type -eq 'commit' -and $p.Tag.object.sha -eq $commit) 'Public tag points at foreign commit'
 $a=@($p.Release.assets|Where-Object{$_.name -eq $jar -and [long]$_.size -eq $size -and $_.digest -eq "sha256:$sha" -and $_.state -eq 'uploaded'})
 Check ($a.Count -eq 1) 'Public JAR asset differs'
 $body=[string]$p.Release.body
 Check ($body.Contains($origin) -and $body.Contains($commit) -and $body.Contains($sha)) 'Release lacks truthful dual provenance'
 Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $tmp -MaximumRedirection 10 -TimeoutSec 180
 JarProof $tmp 'PUBLIC_ANONYMOUS'
}
function EnsureGh(){
 $command=Get-Command gh.exe -ErrorAction SilentlyContinue
 if($null -eq $command){$command=Get-Command gh -ErrorAction SilentlyContinue}
 if($null -ne $command){$script:gh=$command.Source}
 else{
  foreach($p in @((Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\GitHub CLI\gh.exe'),(Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\gh.exe'))){
   if(Test-Path -LiteralPath $p){$script:gh=$p;break}
  }
 }
 if(-not $script:gh){
  $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
  Check ($null -ne $winget) 'Install GitHub CLI first; winget unavailable'
  & $winget.Source install --id GitHub.cli --exact --source winget --silent --accept-source-agreements --accept-package-agreements
  Check ($LASTEXITCODE -eq 0) 'winget GitHub CLI installation failed'
  foreach($p in @((Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\GitHub CLI\gh.exe'),(Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\gh.exe'))){
   if(Test-Path -LiteralPath $p){$script:gh=$p;break}
  }
  Check ([bool]$script:gh) 'GitHub CLI installed; restart PowerShell and repeat the same command'
 }
 $old=$ErrorActionPreference
 try{$ErrorActionPreference='Continue';$null=& $script:gh auth status --hostname github.com 2>&1;$code=$LASTEXITCODE}
 finally{$ErrorActionPreference=$old}
 if($code -ne 0){
  Write-Host 'One-time GitHub browser authentication required.'
  & $script:gh auth login --hostname github.com --git-protocol https --web
  Check ($LASTEXITCODE -eq 0) 'GitHub authorization incomplete'
 }
}
function Test-Identity(){
 Check ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'Requires real Windows PowerShell 5.1'
 $a=[pscustomobject]@{id=536430211;name=$jar;size=$size;digest="sha256:$sha";state='uploaded'}
 $r=[pscustomobject]@{id=379240422;tag_name=$tag;draft=$false;target_commitish=$origin;assets=@($a)}
 $t=[pscustomobject]@{object=[pscustomobject]@{type='commit';sha=$origin}}
 SourceProof $r $t;$a.digest='sha256:bad';$rejected=$false
 try{SourceProof $r $t}catch{$rejected=$true};Check $rejected 'Forged artifact digest accepted'
 $a.digest="sha256:$sha";$t.object.sha='0000000000000000000000000000000000000000';$rejected=$false
 try{SourceProof $r $t}catch{$rejected=$true};Check $rejected 'Forged source tag accepted'
 Write-Host 'VC290_PS51_SELFTEST_PASS: two adversarial source/asset checks'
}
if($SelfTest){Test-Identity;return}
Check ($PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'Use powershell.exe 5.1, not pwsh 7'
$tmp=Join-Path ([IO.Path]::GetTempPath()) ('vc290-'+[guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path $tmp
try{
 $script:stage='public-preflight';$head=Head;Manifest $head;$old=State
 Write-Host "VC290_PUBLIC_HEAD: $head"
 if($PublicPreflight){Write-Host "VC290_PUBLIC_PREFLIGHT_PASS: releasePresent=$($null -ne $old.Release) tagPresent=$($null -ne $old.Tag)";return}
 $script:stage='original-private-read';EnsureGh
 SourceProof (GhJson "repos/$src/releases/tags/$tag") (GhJson "repos/$src/git/ref/tags/$tag")
 $file=Join-Path $tmp $jar
 $null=Gh @('release','download',$tag,'--repo',$src,'--pattern',$jar,'--dir',$tmp)
 JarProof $file 'ORIGINAL_PRIVATE'
 $readback=Join-Path $tmp 'public-readback.jar'
 $script:stage='public-observation'
 if($null -ne $old.Release){PublicProof $old $head $readback;Write-Host "VC290_COMPLETE_NOOP: $url";return}
 if($VerifyOnly){Write-Host 'VC290_VERIFY_PASS: original qualified, no publication';return}
 $script:stage='public-publication'
 Check ((Head) -eq $head) 'Public main moved; no mutation'
 $latest=State;Check ($null -eq $latest.Release) 'Public release appeared; refusing overwrite'
 if($null -ne $latest.Tag){Check ($latest.Tag.object.type -eq 'commit' -and $latest.Tag.object.sha -eq $head) 'Public tag is foreign'}
 else{$null=Gh @('api','-X','POST',"repos/$dst/git/refs",'-f',"ref=refs/tags/$tag",'-f',"sha=$head");Write-Host "VC290_PUBLIC_DISTRIBUTION_TAG_CREATED: $head"}
 $notes=@"
Original qualified VanillaCord 2.9.0 JAR relocation; NO rebuild.
Private producer promotion commit $origin, private release 379240422, original asset 536430211.
Original sha256 $sha length $size bytes. Public distribution tag $tag points at reviewed public projection commit $head.
Public tag is NOT the original private build commit. NO private Git history exported.
Original supported release includes Minecraft 26.2, not an inferred 26.3 PASS.
Authority: https://github.com/SupraCraft/VanillaCord-private/issues/79
Consumer: https://github.com/SupraCraft/mc-server-images/issues/55
"@
 $notesFile=Join-Path $tmp 'release-notes.txt'
 [IO.File]::WriteAllText($notesFile,$notes,(New-Object Text.UTF8Encoding($false)))
 $null=Gh @('release','create',$tag,$file,'--repo',$dst,'--verify-tag','--title','VanillaCord 2.9.0 (original asset relocation)','--notes-file',$notesFile)
 $script:stage='independent-public-readback'
 PublicProof (State) $head $readback
 Write-Host "VC290_PUBLIC_RELEASE_PASS: $url"
 Write-Host 'NEXT: qualify patched vanilla 26.3 boot, restart, world persistence, then Velocity/Paper integration.'
}catch{Write-Host "VC290_FAILED: $($_.Exception.Message)" -ForegroundColor Red;throw}
finally{if(Test-Path -LiteralPath $tmp){Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue}}
