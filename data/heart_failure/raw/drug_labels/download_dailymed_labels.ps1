$ErrorActionPreference = "Stop"

$drugs = @(
    @{ slug = "dapagliflozin"; query = "DAPAGLIFLOZIN"; required = @("DAPAGLIFLOZIN", "TABLET"); exclude = @(" AND ") },
    @{ slug = "empagliflozin"; query = "EMPAGLIFLOZIN"; required = @("EMPAGLIFLOZIN", "TABLET"); exclude = @(" AND ") },
    @{ slug = "spironolactone"; query = "SPIRONOLACTONE"; required = @("SPIRONOLACTONE", "TABLET"); exclude = @(" AND ", "HYDROCHLOROTHIAZIDE") },
    @{ slug = "eplerenone"; query = "EPLERENONE"; required = @("EPLERENONE", "TABLET"); exclude = @(" AND ") },
    @{ slug = "sacubitril_and_valsartan"; query = "SACUBITRIL AND VALSARTAN"; required = @("SACUBITRIL", "VALSARTAN", "TABLET"); exclude = @() },
    @{ slug = "enalapril_maleate"; query = "ENALAPRIL MALEATE"; required = @("ENALAPRIL", "MALEATE", "TABLET"); exclude = @(" AND ") },
    @{ slug = "valsartan"; query = "VALSARTAN"; required = @("VALSARTAN", "TABLET"); exclude = @(" AND ", "SACUBITRIL", "AMLODIPINE", "HYDROCHLOROTHIAZIDE") },
    @{ slug = "carvedilol"; query = "CARVEDILOL"; required = @("CARVEDILOL", "TABLET"); exclude = @(" AND ") },
    @{ slug = "bisoprolol_fumarate"; query = "BISOPROLOL FUMARATE"; required = @("BISOPROLOL", "FUMARATE", "TABLET"); exclude = @(" AND ", "HYDROCHLOROTHIAZIDE") },
    @{ slug = "metoprolol_succinate"; query = "METOPROLOL SUCCINATE"; required = @("METOPROLOL", "SUCCINATE", "EXTENDED", "RELEASE"); exclude = @(" AND ") },
    @{ slug = "furosemide"; query = "FUROSEMIDE"; required = @("FUROSEMIDE", "TABLET"); exclude = @(" AND ", "ANIMAL", "ZYVET") },
    @{ slug = "ivabradine"; query = "IVABRADINE"; required = @("IVABRADINE", "TABLET"); exclude = @(" AND ") },
    @{ slug = "digoxin"; query = "DIGOXIN"; required = @("DIGOXIN", "TABLET"); exclude = @(" AND ") },
    @{ slug = "apixaban"; query = "APIXABAN"; required = @("APIXABAN", "TABLET"); exclude = @(" AND ") },
    @{ slug = "warfarin_sodium"; query = "WARFARIN SODIUM"; required = @("WARFARIN", "SODIUM", "TABLET"); exclude = @(" AND ") },
    @{ slug = "torsemide"; query = "TORSEMIDE"; required = @("TORSEMIDE", "TABLET"); exclude = @(" AND ") },
    @{ slug = "bumetanide"; query = "BUMETANIDE"; required = @("BUMETANIDE", "TABLET"); exclude = @(" AND ") },
    @{ slug = "hydralazine_hydrochloride"; query = "HYDRALAZINE HYDROCHLORIDE"; required = @("HYDRALAZINE", "HYDROCHLORIDE", "TABLET"); exclude = @(" AND ", "ISOSORBIDE") },
    @{ slug = "isosorbide_dinitrate"; query = "ISOSORBIDE DINITRATE"; required = @("ISOSORBIDE", "DINITRATE", "TABLET"); exclude = @(" AND ", "HYDRALAZINE") },
    @{ slug = "losartan_potassium"; query = "LOSARTAN POTASSIUM"; required = @("LOSARTAN", "POTASSIUM", "TABLET"); exclude = @(" AND ", "HYDROCHLOROTHIAZIDE", "AMLODIPINE") },
    @{ slug = "candesartan_cilexetil"; query = "CANDESARTAN CILEXETIL"; required = @("CANDESARTAN", "CILEXETIL", "TABLET"); exclude = @(" AND ", "HYDROCHLOROTHIAZIDE") },
    @{ slug = "finerenone"; query = "FINERENONE"; required = @("FINERENONE", "TABLET"); exclude = @(" AND ") },
    @{ slug = "patiromer"; query = "PATIROMER"; required = @("PATIROMER", "POWDER"); exclude = @(" AND ") },
    @{ slug = "sodium_zirconium_cyclosilicate"; query = "SODIUM ZIRCONIUM CYCLOSILICATE"; required = @("SODIUM", "ZIRCONIUM", "CYCLOSILICATE", "POWDER"); exclude = @(" AND ") }
)

$base = "https://dailymed.nlm.nih.gov/dailymed"
$manifest = [System.Collections.Generic.List[object]]::new()

function Get-DailyMedSplCandidates {
    param([string]$Query)

    $encoded = [System.Uri]::EscapeDataString($Query)
    $url = "$base/services/v2/spls.json?drug_name=$encoded&name_type=generic&pagesize=100"
    $response = Invoke-RestMethod -Uri $url
    if ($null -eq $response.data) {
        $url = "$base/services/v2/spls.json?drug_name=$encoded&name_type=both&pagesize=100"
        $response = Invoke-RestMethod -Uri $url
    }
    return @($response.data)
}

function Select-BestCandidate {
    param(
        [object[]]$Candidates,
        [string[]]$RequiredTerms,
        [string[]]$ExcludedTerms
    )

    $matches = @($Candidates | Where-Object {
        $title = $_.title.ToUpperInvariant()
        foreach ($term in $RequiredTerms) {
            if (-not $title.Contains($term.ToUpperInvariant())) {
                return $false
            }
        }
        foreach ($term in $ExcludedTerms) {
            if ($title.Contains($term.ToUpperInvariant())) {
                return $false
            }
        }
        return $true
    })

    return $matches | Sort-Object @{ Expression = { [datetime]::Parse($_.published_date) }; Descending = $true }, @{ Expression = { [int]$_.spl_version }; Descending = $true } | Select-Object -First 1
}

foreach ($drug in $drugs) {
    Write-Host "Searching $($drug.slug)..."
    $candidates = Get-DailyMedSplCandidates -Query $drug.query
    if ($candidates.Count -eq 0) {
        Write-Warning "No DailyMed SPL found for $($drug.query)"
        continue
    }

    $best = Select-BestCandidate -Candidates $candidates -RequiredTerms $drug.required -ExcludedTerms $drug.exclude
    if ($null -eq $best) {
        Write-Warning "No matching DailyMed SPL found for $($drug.query)"
        continue
    }

    $dir = Join-Path $PSScriptRoot $drug.slug
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    $xmlPath = Join-Path $dir "$($drug.slug)_label.xml"
    $pdfPath = Join-Path $dir "$($drug.slug)_label.pdf"
    $xmlUrl = "$base/services/v2/spls/$($best.setid).xml"
    $pdfUrl = "$base/downloadpdffile.cfm?setId=$($best.setid)"

    Write-Host "Downloading $($drug.slug): $($best.title)"
    Invoke-WebRequest -Uri $xmlUrl -OutFile $xmlPath
    Invoke-WebRequest -Uri $pdfUrl -OutFile $pdfPath

    $manifest.Add([pscustomobject]@{
        slug = $drug.slug
        query = $drug.query
        setid = $best.setid
        spl_version = $best.spl_version
        published_date = $best.published_date
        title = $best.title
        xml = "$($drug.slug)/$($drug.slug)_label.xml"
        pdf = "$($drug.slug)/$($drug.slug)_label.pdf"
    })
}

$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $PSScriptRoot "download_manifest.json") -Encoding UTF8
Write-Host "Done. Saved $($manifest.Count) labels."
