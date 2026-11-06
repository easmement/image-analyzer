"use client";
import Alert from "@mui/material/Alert";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import AddLibraryForm from "./AddLibraryForm";
import LibraryCard from "./LibraryCard";

export default function LibrariesPanel() {
  const { data, error, isPending } = useQuery({ queryKey: ["libraries"], queryFn: api.libraries });

  return (
    <Stack spacing={3}>
      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add a folder
          </Typography>
          <AddLibraryForm />
        </CardContent>
      </Card>

      {error && <Alert severity="error">Couldn’t load libraries: {error.message}</Alert>}
      {isPending && <Skeleton variant="rounded" height={150} />}
      {data?.length === 0 && (
        <Typography color="text.secondary">No libraries yet. Add a folder above to start.</Typography>
      )}
      {data?.map((library) => <LibraryCard key={library.id} library={library} />)}
    </Stack>
  );
}
