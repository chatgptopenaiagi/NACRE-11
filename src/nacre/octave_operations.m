% Nacre owned fixed-operation worker, invoked via public Octave Courier API.
1;
function a = decode_matrix (item)
  if (item.rows < 1 || item.rows > 64 || item.columns < 1 || item.columns > 64 || ...
      item.rows != fix(item.rows) || item.columns != fix(item.columns) || ...
      !isnumeric(item.values) || !isreal(item.values) || any(!isfinite(item.values(:))) || ...
      numel(item.values) != item.rows * item.columns)
    error ("Invalid finite real matrix envelope");
  endif
  a = reshape(item.values, item.columns, item.rows).';
endfunction

function item = encode_matrix (a)
  if (!isreal(a) || any(!isfinite(a(:))))
    error ("Operation produced unsupported complex or nonfinite output");
  endif
  item = struct("rows", rows(a), "columns", columns(a), "values", reshape(a.', 1, []));
endfunction

args = argv();
if (numel(args) != 2), error("Expected request and response paths"); endif
request = jsondecode(fileread(args{1}));
if (request.schema_version != 1), error("Unsupported request schema"); endif
response = struct("schema_version", 1, "operation", request.operation, "octave_version", version());
switch (request.operation)
  case "inverse"
    a = decode_matrix(request.a);
    if (rows(a) != columns(a)), error("Inverse requires square matrix"); endif
    response.rcond = rcond(a);
    if (response.rcond <= 1e-10), error("Singular or ill-conditioned matrix"); endif
    response.result = encode_matrix(inv(a));
  case "qr"
    a = decode_matrix(request.a);
    [q, r] = qr(a, 0);
    response.q = encode_matrix(q); response.r = encode_matrix(r);
  case "eigen"
    a = decode_matrix(request.a);
    if (rows(a) != columns(a) || !isequal(a, a.')), error("Eigen accepts exactly real symmetric matrices"); endif
    [v, d] = eig(a);
    response.vectors = encode_matrix(v); response.values = encode_matrix(diag(d));
  case "polynomial"
    coefficients = decode_matrix(request.coefficients); points = decode_matrix(request.points);
    response.result = encode_matrix(polyval(coefficients, points));
  case "regression"
    x = decode_matrix(request.x); y = decode_matrix(request.y);
    if (rows(x) < columns(x) || rows(x) != rows(y) || columns(y) != 1), error("Invalid regression dimensions"); endif
    [q, r] = qr(x, 0); response.rcond = rcond(r);
    if (response.rcond <= 1e-10), error("Rank deficient or ill-conditioned design matrix"); endif
    coefficients = r \ (q.' * y);
    response.coefficients = encode_matrix(coefficients); response.fitted = encode_matrix(x * coefficients);
  case "fft"
    values = decode_matrix(request.values); result = fft(values);
    response.real = encode_matrix(real(result)); response.imaginary = encode_matrix(imag(result));
  otherwise
    error("Unsupported bounded operation");
endswitch
text = jsonencode(response);
[fid, message] = fopen(args{2}, "w");
if (fid < 0), error(message); endif
unwind_protect
  if (fwrite(fid, text, "char") != numel(text)), error("Incomplete response write"); endif
unwind_protect_cleanup
  fclose(fid);
end_unwind_protect
