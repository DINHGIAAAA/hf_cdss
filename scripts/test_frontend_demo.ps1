param(
    [string]$ApiBase = "http://localhost:8000",
    [string]$FrontendUrl = "http://localhost:5173",
    [string]$ApiKey = "change-me",
    [ValidateSet("hf_ckd", "mra_safety")]
    [string]$Case = "hf_ckd"
)

$ErrorActionPreference = "Stop"

function Invoke-CdssJson {
    param(
        [string]$Method,
        [string]$Uri,
        [object]$Body = $null
    )

    $headers = @{ "x-api-key" = $ApiKey }
    if ($Body -ne $null) {
        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30)
    }
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
}

Write-Host "== HF CDSS UI Demo Smoke Test ==" -ForegroundColor Cyan
Write-Host "Frontend: $FrontendUrl"
Write-Host "Backend:  $ApiBase"
Write-Host ""

Write-Host "1) Backend readiness" -ForegroundColor Yellow
$ready = Invoke-CdssJson -Method GET -Uri "$ApiBase/health/ready"
$ready | ConvertTo-Json -Depth 8
Write-Host ""

Write-Host "2) Retrieval smoke test" -ForegroundColor Yellow
$retrieval = Invoke-CdssJson -Method GET -Uri "$ApiBase/api/v1/retrieval/search?q=heart%20failure%20sglt2%20egfr&top_k=3"
$retrieval.evidence_chunks | ForEach-Object {
    Write-Host "- $($_.document_id) | page=$($_.page) | score=$([math]::Round($_.score, 3))"
    Write-Host "  $($_.source_link)"
}
Write-Host ""

if ($Case -eq "hf_ckd") {
    $message = "Benh nhan HFrEF EF 28%, CKD eGFR 48, HA tam thu 88, HR 54, dang dung metoprolol, furosemide, apixaban. Co the toi uu GDMT the nao?"
    $patient = @{
        patient_identity = @{ case_id = "UI_DEMO_HF_CKD_001" }
        demographics = @{ age = 68; sex = "male" }
        heart_failure_profile = @{ lvef = @{ value = 28; unit = "%" }; nyha_class = "III" }
        labs = @{
            egfr = @{ value = 48; unit = "mL/min/1.73m2" }
            potassium = @{ value = 4.9; unit = "mmol/L" }
        }
        vitals = @{
            systolic_bp = @{ value = 88; unit = "mmHg" }
            heart_rate = @{ value = 54; unit = "bpm" }
            weight_kg = @{ value = 72; unit = "kg" }
        }
        conditions = @(
            @{ name = "HFrEF"; status = "active" },
            @{ name = "CKD"; status = "active" },
            @{ name = "atrial fibrillation"; status = "active" }
        )
        medications = @(
            @{ name = "metoprolol succinate"; status = "active" },
            @{ name = "furosemide"; status = "active" },
            @{ name = "apixaban"; status = "active" }
        )
        allergy_statements = @(@{ substance = "no known drug allergies"; status = "active" })
        red_flags = @(@{ name = "stable"; status = "absent" })
        care_context = @{ clinician_question = $message; decision_context = "demo smoke test" }
    }
    $attachmentText = @"
Cardiology clinic note, de-identified demo.
Assessment: chronic HFrEF, LVEF 28%, NYHA III symptoms. CKD stage 3a, atrial fibrillation.
Vitals: BP 88/58 mmHg, HR 54 bpm, weight 72 kg.
Labs: eGFR 48 mL/min/1.73m2, potassium 4.9 mmol/L.
Current meds: metoprolol succinate, furosemide, apixaban.
Question: optimize GDMT while avoiding hypotension and bradycardia.
"@
} else {
    $message = "Dang dung spironolactone, eGFR 24 va kali 5.7. Co nen tiep tuc hay tang lieu MRA khong?"
    $patient = @{
        patient_identity = @{ case_id = "UI_DEMO_MRA_002" }
        demographics = @{ age = 71; sex = "female" }
        heart_failure_profile = @{ lvef = @{ value = 30; unit = "%" }; nyha_class = "III" }
        labs = @{
            egfr = @{ value = 24; unit = "mL/min/1.73m2" }
            potassium = @{ value = 5.7; unit = "mmol/L" }
        }
        vitals = @{
            systolic_bp = @{ value = 104; unit = "mmHg" }
            heart_rate = @{ value = 70; unit = "bpm" }
            weight_kg = @{ value = 61; unit = "kg" }
        }
        conditions = @(
            @{ name = "HFrEF"; status = "active" },
            @{ name = "CKD"; status = "active" },
            @{ name = "diabetes"; status = "active" }
        )
        medications = @(
            @{ name = "spironolactone"; status = "active" },
            @{ name = "furosemide"; status = "active" },
            @{ name = "warfarin"; status = "active" }
        )
        allergy_statements = @(@{ substance = "no known drug allergies"; status = "active" })
        red_flags = @(@{ name = "hyperkalemia"; status = "present" })
        care_context = @{ clinician_question = $message; decision_context = "demo smoke test" }
    }
    $attachmentText = @"
Nephro-cardiology follow-up, de-identified demo.
Assessment: HFrEF with advanced CKD and hyperkalemia.
Vitals: BP 104/64 mmHg, HR 70 bpm, weight 61 kg.
Labs: eGFR 24 mL/min/1.73m2, potassium 5.7 mmol/L.
Current meds: spironolactone, furosemide, warfarin.
Question: evaluate MRA safety and whether dose escalation is appropriate.
"@
}

Write-Host "3) Chat + attachment smoke test: $Case" -ForegroundColor Yellow
$payload = @{
    message = $message
    language = "vi"
    patient = $patient
    clinical_attachments = @(
        @{
            file_name = "$Case-demo-note.txt"
            mime_type = "text/plain"
            extracted_text = $attachmentText
        }
    )
}
$chat = Invoke-CdssJson -Method POST -Uri "$ApiBase/api/v1/chat" -Body $payload
Write-Host "conversation_id: $($chat.conversation_id)"
Write-Host "status: $($chat.status)"
Write-Host "assistant:"
Write-Host $chat.assistant_message.content
Write-Host ""

if ($chat.verification.evidence_chunks) {
    Write-Host "Evidence:" -ForegroundColor Yellow
    $chat.verification.evidence_chunks | Select-Object -First 5 | ForEach-Object {
        Write-Host "- $($_.document_id) | $($_.section)"
        Write-Host "  $($_.source_link)"
    }
}

Write-Host ""
Write-Host "Open UI manually: $FrontendUrl" -ForegroundColor Green
