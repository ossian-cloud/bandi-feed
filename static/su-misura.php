<?php
// A feed for any combination of the search page's filters, from su-misura.json (written by build.py).
// Reads nothing but the query string, stores nothing, sets no cookies.
// ?r=Regione &p=Provincia &n=Lavori|Servizi|Forniture &c=CPV division (2 digits) &q=words &v=minimum value in euro
declare(strict_types=1);

const MAX_ENTRIES = 200;

function fail(int $code, string $msg): never {
    http_response_code($code);
    header('Content-Type: text/plain; charset=utf-8');
    echo $msg, "\n";
    exit;
}

function fold(string $s): string {
    $s = mb_strtolower($s, 'UTF-8');
    if (class_exists('Normalizer')) {
        return preg_replace('/\p{Mn}/u', '', Normalizer::normalize($s, Normalizer::FORM_D));
    }
    return strtr($s, ['à' => 'a', 'á' => 'a', 'è' => 'e', 'é' => 'e', 'ì' => 'i', 'í' => 'i',
                      'ò' => 'o', 'ó' => 'o', 'ù' => 'u', 'ú' => 'u', 'ä' => 'a', 'ö' => 'o', 'ü' => 'u']);
}

function x(string $s): string {
    return htmlspecialchars($s, ENT_XML1 | ENT_QUOTES, 'UTF-8');
}

$raw = @file_get_contents(__DIR__ . '/su-misura.json');
$D = $raw === false ? null : json_decode($raw, true);
if (!is_array($D)) fail(503, 'Dati non disponibili, riprova più tardi.');

$get = fn(string $k): string => is_string($_GET[$k] ?? null) ? trim($_GET[$k]) : '';
$r = $get('r'); $p = $get('p'); $n = $get('n'); $c = $get('c'); $q = $get('q'); $v = $get('v');
if ($r !== '' && !in_array($r, $D['regions'], true)) fail(400, 'Regione non valida.');
if ($n !== '' && !in_array($n, ['Lavori', 'Servizi', 'Forniture'], true)) fail(400, 'Tipo non valido.');
if ($c !== '' && !isset($D['sectors'][$c])) fail(400, 'Settore CPV non valido: usa le prime due cifre, per esempio 72.');
if (mb_strlen($p) > 60 || mb_strlen($q) > 120) fail(400, 'Parametro troppo lungo.');
if ($v !== '' && !ctype_digit($v)) fail(400, 'Importo non valido: solo cifre, in euro.');
$vmin = $v === '' ? 0 : (int)$v;

// words, as on the search page: SOA categories ("OG 3", "os12-a") are one token matched exactly, other words are substrings
$fq = fold($q);
$soa = [];
$fq = preg_replace_callback('/\bo([gs])\s*(\d+)(-[a-z]+)?\b/u', function ($m) use (&$soa) {
    $soa[] = '/(^|[^a-z0-9])o' . $m[1] . ' ' . $m[2] . (isset($m[3]) && $m[3] !== '' ? preg_quote($m[3], '/') : '(-[a-z]+)?') . '(?![0-9a-z-])/u';
    return ' ';
}, $fq);
$words = preg_split('/\s+/u', $fq, -1, PREG_SPLIT_NO_EMPTY);

$out = [];
foreach ($D['rows'] as $row) {
    if (($r !== '' && !in_array($r, $row['r'], true)) || ($p !== '' && !in_array($p, $row['p'], true))
        || ($n !== '' && !in_array($n, $row['n'], true)) || ($c !== '' && !in_array($c, $row['c'], true))
        || $row['v'] < $vmin) continue;
    foreach ($words as $w) if (!str_contains($row['t'], $w)) continue 2;
    foreach ($soa as $re) if (!preg_match($re, $row['t'])) continue 2;
    $out[] = $row['x'];
    if (count($out) >= MAX_ENTRIES) break;
}

$params = array_filter(['r' => $r, 'p' => $p, 'n' => $n, 'c' => $c, 'q' => $q, 'v' => $v], fn($s) => $s !== '');
ksort($params);
$qs = http_build_query($params, '', '&', PHP_QUERY_RFC3986);
$self = $D['base'] . '/feed/su-misura.php' . ($qs !== '' ? '?' . $qs : '');
$search = $D['base'] . '/cerca.html' . ($qs !== '' ? '#' . $qs : '');
$label = [];
if ($p !== '') $label[] = $p; elseif ($r !== '') $label[] = $r;
if ($n !== '') $label[] = $n;
if ($c !== '') $label[] = "settore CPV $c";
if ($q !== '') $label[] = "«{$q}»";
if ($vmin > 0) $label[] = 'da ' . number_format($vmin, 0, ',', '.') . ' €';
$title = 'Bandi pubblici · ' . ($label ? implode(' · ', $label) : 'Tutta Italia');

header('Content-Type: application/atom+xml; charset=utf-8');
header('Cache-Control: public, max-age=1800');
header('X-Robots-Tag: noindex');
echo '<?xml version="1.0" encoding="utf-8"?>', "\n",
     '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="it">', "\n",
     '  <id>', x($self), "</id>\n",
     '  <title>', x($title), "</title>\n",
     '  <subtitle>', x($D['subtitle']), "</subtitle>\n",
     '  <link rel="self" type="application/atom+xml" href="', x($self), "\"/>\n",
     '  <link rel="alternate" type="text/html" href="', x($search), "\"/>\n",
     '  <updated>', x($D['updated']), "</updated>\n",
     '  <rights>', x($D['rights']), "</rights>\n",
     "  <author><name>Ossian (AI agent)</name><uri>https://ossian.cloud</uri></author>\n",
     '  <generator uri="https://ossian.cloud/bandi/">ossian bandi feed</generator>', "\n";
foreach ($out as $e) echo $e, "\n";
echo "</feed>\n";
