package MyDB;

use strict;
use warnings;

use Exporter;

our @ISA= qw( Exporter );
# these CAN be exported.
our @EXPORT_OK = qw( add_record query_records code_nl decode_nl modify_record
    DB_ISSUES DB_COMMENTS DB_TRANSITIONS DB_ADMINS);
# these are exported by default.
our @EXPORT = qw( add_record query_records code_nl decode_nl modify_record
    DB_ISSUES DB_COMMENTS DB_TRANSITIONS DB_ADMINS);
    
use constant DB_ROOT => 'db/';
use constant DB_ISSUES => DB_ROOT . 'issues';
use constant DB_COMMENTS => DB_ROOT . 'comments';
use constant DB_TRANSITIONS => DB_ROOT . 'transitions';
use constant DB_ADMINS => DB_ROOT . 'admins';

sub add_record {
    my ($db, $data) = @_;
    db_create($db);
    tie my @lines, "Tie::File", $db;
    #reading id_count
    my $id = $lines[0];
    die "First line of $db is corrupted.\n" unless Scalar::Util::looks_like_number($id);
    #changing id_count in db 
    $lines[0] = $id+1;
    #pushing record
    my $record = join(',',$id,$data);
    push @lines, "$record\n";
    #saving file
    untie @lines;
    return $id;
}

sub modify_record {
    die "Wrong call of modify_record" unless @_ == 5;
    my ($db, $q_idx, $query, $v_idx, $value) = @_;
    tie my @lines, "Tie::File", $db;
    #omit id_count
    my $id_count = shift @lines;
    foreach my $line(@lines) {
        my @record = split(',',$line);
        if ($record[$q_idx] eq $query) {
            #match
            $record[$v_idx] = $value;
            $line = join(',',@record);
        }
    }
    unshift @lines, $id_count;
    #saving file
    untie @lines;
}

sub query_records {
    my ($db, $idx, $query) = @_;
    open my $in_fh, '<', $db or die "Cannot open $db in read mode.\n";
    #omit first line
    <$in_fh>;
    my @records = ();
    while (my $line = <$in_fh>) {
        chomp $line;
        my @values = split(',',$line);
        if ($idx eq 'all' or $values[$idx] eq $query) {
            push(@records, \@values);
        }
    }
    return @records;
}

sub db_create {
    my ($db) = @_;     
    #conditional file creation if not existing
    if (not -f $db) {
        open my $out_fh, '>', $db or die "Cannot open $db in write mode.\n";
        print $out_fh "1\n";
        close $out_fh;
    }
}

sub code_nl {
    my $text = $_[0];
    $text =~ s/\r\n/%nl%/g;
    $text =~ s/,/%c%/g;
    return $text;
}

sub decode_nl {
    my $text = $_[0];
    $text =~ s/%nl%/\r\n/g;
    $text =~ s/%c%/,/g;
    return $text;
}

1;