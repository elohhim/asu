#!/usr/bin/perl
use strict;
use warnings;
use Scalar::Util;
#use Crypt::PBKDF2;
use Digest::SHA qw(sha512_base64);
use Tie::File;
use Term::ReadKey;
use MyDB;

#checking arguments
die "Usage: addadmin <name> <e-mail>\n" unless @ARGV == 2;
my ($name, $email) = @ARGV;
ReadMode('noecho');
print "Password: ";
chomp (my $password = <STDIN>);
print "\nRepeat password: ";
chomp (my $repeat = <STDIN>);
print "\n";
die "Passwords don't match.\n" unless $repeat eq $password;
ReadMode(0);

#hashing password
#my $pbkdf2=Crypt::PBKDF2->new(
#   hash_class => 'HMACSHA2',
#    hash_args => {
#        sha_size => 512,
#    },
#    iterations => 10000,
#    salt_len => 10,
#);
#my $hash = $pbkdf2->generate($password);
my $hash = sha512_base64($password);

#conditional file creation
if (not -f DB_ADMINS) {
    print "Creating admins file at DB_ADMINS.\n";
    open my $out_fh, '>', DB_ADMINS or die "Cannot open DB_ADMINS(".DB_ADMINS.") in write mode.\n";
    print $out_fh "0\n";
    close $out_fh;
}

#reading id
open my $in_fh, '<', DB_ADMINS or die "Cannot open DB_ADMINS in read mode.\n";
my $firstline = <$in_fh>;    
chomp $firstline;
die "First line of DB_ADMINS is corrupted.\n" unless Scalar::Util::looks_like_number($firstline);
my $id = $firstline;

#checking if name already exist
while (<$in_fh> ) {
    chomp;
    if((split( ',', $_) )[1] eq $name) {
        die "Name already in database.\n";
    }
}
close $in_fh;

#saving to file
tie my @lines, "Tie::File", DB_ADMINS;
$lines[0] = $id+1;
my $record = join(',', $id, $name, $hash, $email);
push @lines, "$record\n";
untie @lines;
print "Added $name to database.\n";