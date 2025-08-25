# Check Windows Bluetooth status and configuration

Write-Host "Checking Windows Bluetooth Status..." -ForegroundColor Cyan

# Check if Bluetooth service is running
$btService = Get-Service -Name "bthserv" -ErrorAction SilentlyContinue
if ($btService) {
    Write-Host "Bluetooth Support Service: $($btService.Status)" -ForegroundColor $(if ($btService.Status -eq 'Running') {'Green'} else {'Red'})
} else {
    Write-Host "Bluetooth Support Service: Not Found" -ForegroundColor Red
}

# Check Bluetooth radio status
Write-Host "`nChecking Bluetooth Radio Status..." -ForegroundColor Cyan
Get-PnpDevice -Class Bluetooth | Select-Object Status, FriendlyName | Format-Table

# Check for Bluetooth adapters
Write-Host "`nBluetooth Adapters:" -ForegroundColor Cyan
Get-PnpDevice -FriendlyName "*Bluetooth*" | Where-Object {$_.Status -eq "OK"} | Select-Object FriendlyName, Status | Format-Table

# Check Windows version
Write-Host "`nWindows Version:" -ForegroundColor Cyan
[System.Environment]::OSVersion.Version

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
Write-Host "`nRunning as Administrator: $isAdmin" -ForegroundColor $(if ($isAdmin) {'Green'} else {'Yellow'})

if (-not $isAdmin) {
    Write-Host "Note: Some Bluetooth operations may require Administrator privileges" -ForegroundColor Yellow
}