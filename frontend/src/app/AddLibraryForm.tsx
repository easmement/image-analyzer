"use client";
import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function AddLibraryForm() {
  const queryClient = useQueryClient();
  const [path, setPath] = useState("");
  const [name, setName] = useState("");

  const create = useMutation({
    mutationFn: () => api.createLibrary({ path: path.trim(), name: name.trim() || null }),
    onSuccess: async (library) => {
      setPath("");
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["libraries"] });
      // Start indexing straight away; the card picks up the job via active_job_id.
      await api.startScan(library.id);
      await queryClient.invalidateQueries({ queryKey: ["libraries"] });
    },
  });

  return (
    <Stack
      component="form"
      spacing={2}
      onSubmit={(e) => {
        e.preventDefault();
        if (path.trim()) create.mutate();
      }}
    >
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField
          label="Folder path"
          placeholder="/home/you/Pictures"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          helperText="Absolute path on this machine. Files are only read, never changed."
          fullWidth
          required
        />
        <TextField
          label="Name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          sx={{ minWidth: { sm: 200 } }}
        />
      </Stack>
      {create.error && <Alert severity="error">{create.error.message}</Alert>}
      <div>
        <Button type="submit" variant="contained" loading={create.isPending} disabled={!path.trim()}>
          Add and scan
        </Button>
      </div>
    </Stack>
  );
}
