$filePath = "d:\Sukriti RRU\Projects\ShadowPrompt\ShadowPrompt_Blueprint (1).docx"
$outPath = "d:\Sukriti RRU\Projects\ShadowPrompt\blueprint_text.txt"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$doc = $word.Documents.Open($filePath)
$text = $doc.Content.Text
$text | Out-File -FilePath $outPath -Encoding UTF8
$doc.Close()
$word.Quit()
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
Write-Output "Done - saved to $outPath"
