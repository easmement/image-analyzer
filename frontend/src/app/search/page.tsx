import Container from "@mui/material/Container";
import Typography from "@mui/material/Typography";
import SearchView from "./SearchView";

export default function SearchPage() {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Search by image
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Drop in any image to find its copies and look-alikes in your libraries. The image is only
        analysed, never added to a library or kept.
      </Typography>
      <SearchView />
    </Container>
  );
}
