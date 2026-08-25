type FieldProps = {
  id: string;
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
};

export function Field({ id, label, value, placeholder, onChange }: FieldProps) {
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        autoComplete="off"
      />
    </label>
  );
}
